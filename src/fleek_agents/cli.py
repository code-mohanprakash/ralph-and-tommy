"""The `fleek` command: run the marketplace from a terminal.

    fleek negotiate --mock    one buyer: match, negotiate with scripted agents, show the deal

It prints what each side would see, never a secret limit.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy.orm import Session

from fleek_agents.agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.config import Settings
from fleek_agents.domain.fees import buyer_pays, seller_receives
from fleek_agents.domain.models import Lot
from fleek_agents.domain.state import NegotiationState
from fleek_agents.market.seed import generate_market
from fleek_agents.matching.embeddings import Embedder, HashingEmbedder, LocalEmbedder
from fleek_agents.matching.funnel import bundles_for, possible_deals
from fleek_agents.matching.ranking import rank
from fleek_agents.orchestrator.approval import approve as approve_deal
from fleek_agents.orchestrator.approval import pending, settle
from fleek_agents.orchestrator.approval import reject as reject_deal
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.run import run_negotiation
from fleek_agents.safety.scanner import scanner_for
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog
from fleek_agents.store.market import LotRow, hard_filter, load_market
from fleek_agents.vault.seed import generate_mandates

app = typer.Typer(
    help="Ralph and Tommy: agents that negotiate bulk deals on Fleek.", no_args_is_help=True
)
START = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


class Matcher(StrEnum):
    local = "local"  # the bge-small model (downloads 64 MB once)
    words = "words"  # shared words only; instant, for a quick look


@app.callback()
def main() -> None:
    """Ralph and Tommy."""


@app.command()
def negotiate(
    mock: Annotated[
        bool, typer.Option("--mock", help="Scripted agents, no AI or API key.")
    ] = False,
    buyer: Annotated[str, typer.Option(help="Which buyer, e.g. buyer-0001.")] = "buyer-0001",
    seed: Annotated[int, typer.Option(help="Which seeded market.")] = 2026,
    matcher: Annotated[Matcher, typer.Option(help="How to rank lots.")] = Matcher.local,
    db: Annotated[str, typer.Option(help="Keep deals in this file, e.g. fleek.db.")] = "",
) -> None:
    """Match one buyer to a lot, negotiate it, and show the result."""
    console = Console()
    if not mock:
        console.print("The Claude agents aren't built yet. Run with --mock for scripted agents.")
        raise typer.Exit(code=2)

    settings = Settings()
    market = generate_market(seed=seed)
    secrets = generate_mandates(market, seed=seed)
    want = next((w for w in market.wants if w.buyer_id == buyer), None)
    if want is None:
        console.print(f"No buyer called {buyer}. Try buyer-0001 to buyer-{len(market.buyers):04d}.")
        raise typer.Exit(code=2)
    sellers = {s.id: s for s in market.sellers}

    engine = make_engine(f"sqlite:///{db}" if db else "sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        if session.get(LotRow, market.lots[0].id) is None:
            load_market(session, market)
        lines: list[str] = [f"{buyer} wants: {want.text}"]

        passed = hard_filter(session, want)
        possible = possible_deals(session, market, secrets, want)
        embedder: Embedder = LocalEmbedder() if matcher is Matcher.local else HashingEmbedder()
        top = rank(want, possible, embedder)
        lines.append(
            f"Matching: {len(market.lots):,} lots → {len(passed)} pass the filters → "
            f"{len(possible)} could work at some price → top {len(top)} by similarity"
        )
        if not top:
            lines.append("No lot can work for this buyer. Nothing to negotiate, nothing spent.")
            for line in lines:
                console.print(line)
            raise typer.Exit(code=0)

        lots_by_id = {lot.id: lot for lot in market.lots}
        lot = top[0].lot
        bundles = bundles_for(want, lot)
        lines.append(f"Chosen: {lot.title} from {sellers[lot.seller_id].name}, {bundles} bundle(s)")

        log, clock = EventLog(session), FakeClock(START)
        nid = open_negotiation(
            log, buyer_id=buyer, lot_id=lot.id, clock=clock, rules=settings.negotiation
        )
        final = run_negotiation(
            log,
            nid,
            lot=lot,
            seller=sellers[lot.seller_id],
            want=want,
            bundles=bundles,
            buyer_limit=secrets.buyers[buyer],
            seller_limit=secrets.lots[lot.id],
            ralph=ScriptedRalph(),
            tommy=ScriptedTommy(),
            clock=clock,
            settings=settings,
        )

        rows: list[tuple[str, ...]] = []
        public = [lot.base_price, lot.shipping, top[0].quote.base_price]
        for event in log.read(nid):
            who = {"buyer_agent": "Ralph", "seller_agent": "Tommy"}.get(event.by, "Fleek")
            card = event.card
            if card is not None:
                public.append(card.base_price)
            price = str(card.base_price) if card else ""
            bundles_text = str(card.bundles) if card else ""
            round_text = str(card.round) if card else ""
            rows.append((round_text, who, str(event.move), price, bundles_text))

        after: list[str] = []
        if final is NegotiationState.PENDING_APPROVAL:
            agreed = [e.card for e in log.read(nid) if e.card is not None][-1]
            pieces = agreed.bundles * lot.pieces
            paid = buyer_pays(base_price=agreed.base_price, shipping=lot.shipping, pieces=pieces)
            got = seller_receives(base_price=agreed.base_price, pieces=pieces)
            public += [
                paid.total,
                paid.goods,
                paid.protection_fee,
                got.net,
                got.gross,
                got.commission,
            ]
            after.append(
                f"Agreed at {agreed.base_price} a piece for {pieces} pieces, "
                f"inside both secret limits. Waiting for approval."
            )
            fee = paid.protection_fee
            after.append(f"Buyer pays {paid.total} (goods {paid.goods} + protection fee {fee})")
            after.append(
                f"Seller receives {got.net} (base {got.gross} - commission {got.commission})"
            )
            state = settle(log, nid, lots=lots_by_id, rules=settings.approval, at=clock.now())
            if state is NegotiationState.CLOSED:
                after.append("Approved by the rule (a small deal for a buyer with a few deals).")
            else:
                why = next(w.why for w in pending(log, lots_by_id, settings.approval))
                where = f" --db {db}" if db else ""
                after.append(f"Waiting for a person ({why}): fleek approve {nid}{where}")
        else:
            after.append(f"Ended: {final}")

        # Every line a person reads goes through the leak scanner last.
        scanner = scanner_for(secrets.buyers[buyer], secrets.lots[lot.id], public)
        for line in lines:
            console.print(scanner.clean(line))
        table = Table("Round", "Who", "Move", "Base / piece", "Bundles")
        for row in rows:
            table.add_row(*(scanner.clean(cell) for cell in row))
        console.print(table)
        for line in after:
            console.print(scanner.clean(line))


@app.command()
def safety(
    live: Annotated[
        bool, typer.Option("--live", help="Run against Claude again (needs the key).")
    ] = False,
) -> None:
    """Attack the naive design and the protected one the same way; show what leaked."""
    from fleek_agents.llm.env import load_env_file
    from fleek_agents.safety.report import safety_report

    console = Console()
    if live:
        load_env_file()
    source = "live Claude Haiku 5.5" if live else "recorded live runs (no key needed)"
    console.print(f"Safety report, from {source}.")
    rows = safety_report(live=live)
    table = Table("Attack", "Target", "Secret leaked?", "Deal outside a limit?", "What happened")
    for row in rows:
        table.add_row(
            row.attack, row.target, row.leaked, "YES" if row.breach else "no", row.what_happened
        )
    console.print(table)
    naive = [r for r in rows if r.target == "naive seller"]
    protected = [r for r in rows if r.target != "naive seller"]
    leaks = sum(r.leaked in ("exact", "near") for r in naive)
    breaches = sum(r.breach for r in protected)
    console.print(f"Naive seller: secret leaked in {leaks} of {len(naive)} attacks.")
    console.print(
        f"Protected agents: {breaches} deals outside a limit in {len(protected)} attacks."
    )
    console.print("One recorded run per attack on one model: an illustration, not a rate.")


def _session(db: str, seed: int) -> tuple[Session, dict[str, Lot]]:
    market = generate_market(seed=seed)
    engine = make_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)
    return Session(engine), {lot.id: lot for lot in market.lots}


@app.command()
def approvals(
    db: Annotated[str, typer.Option(help="The deals file.")] = "fleek.db",
    seed: Annotated[int, typer.Option(help="Which seeded market.")] = 2026,
) -> None:
    """Deals waiting for a person, and why."""
    session, lots = _session(db, seed)
    waiting = pending(EventLog(session), lots, Settings().approval)
    console = Console()
    if not waiting:
        console.print("Nothing waiting for approval.")
        return
    table = Table("Negotiation", "Buyer", "Lot", "Buyer pays", "Why it's waiting")
    for w in waiting:
        table.add_row(w.negotiation_id, w.buyer_id, w.lot.title, str(w.total), w.why)
    console.print(table)


@app.command()
def approve(
    negotiation: Annotated[str, typer.Argument(help="e.g. neg-0001")],
    db: Annotated[str, typer.Option(help="The deals file.")] = "fleek.db",
) -> None:
    """Approve a waiting deal: it closes."""
    session, _ = _session(db, 2026)
    approve_deal(EventLog(session), negotiation, at=datetime.now(UTC))
    Console().print(f"{negotiation} approved and closed.")


@app.command()
def reject(
    negotiation: Annotated[str, typer.Argument(help="e.g. neg-0001")],
    db: Annotated[str, typer.Option(help="The deals file.")] = "fleek.db",
) -> None:
    """Reject a waiting deal: the lot goes back on sale."""
    session, _ = _session(db, 2026)
    reject_deal(EventLog(session), negotiation, at=datetime.now(UTC))
    Console().print(f"{negotiation} rejected. The lot is back on sale.")
