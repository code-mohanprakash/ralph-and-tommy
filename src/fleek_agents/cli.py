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
from fleek_agents.domain.state import NegotiationState
from fleek_agents.market.seed import generate_market
from fleek_agents.matching.embeddings import Embedder, HashingEmbedder, LocalEmbedder
from fleek_agents.matching.funnel import bundles_for, possible_deals
from fleek_agents.matching.ranking import rank
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.run import run_negotiation
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog
from fleek_agents.store.market import hard_filter, load_market
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

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        load_market(session, market)
        console.rule(f"[bold]{buyer}[/] wants: {want.text}")

        passed = hard_filter(session, want)
        possible = possible_deals(session, market, secrets, want)
        embedder: Embedder = LocalEmbedder() if matcher is Matcher.local else HashingEmbedder()
        top = rank(want, possible, embedder)
        console.print(
            f"Matching: {len(market.lots):,} lots → {len(passed)} pass the filters → "
            f"{len(possible)} could work at some price → top {len(top)} by similarity"
        )
        if not top:
            console.print("No lot can work for this buyer. Nothing to negotiate, nothing spent.")
            raise typer.Exit(code=0)

        lot = top[0].lot
        bundles = bundles_for(want, lot)
        console.print(
            f"Chosen: [bold]{lot.title}[/] from {sellers[lot.seller_id].name}, {bundles} bundle(s)"
        )

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

        table = Table("Round", "Who", "Move", "Base / piece", "Bundles")
        for event in log.read(nid):
            who = {"buyer_agent": "Ralph", "seller_agent": "Tommy"}.get(event.by, "Fleek")
            price = str(event.card.base_price) if event.card else ""
            bundles_text = str(event.card.bundles) if event.card else ""
            round_text = str(event.card.round) if event.card else ""
            table.add_row(round_text, who, event.move, price, bundles_text)
        console.print(table)

        if final is NegotiationState.PENDING_APPROVAL:
            agreed = [e.card for e in log.read(nid) if e.card is not None][-1]
            pieces = agreed.bundles * lot.pieces
            paid = buyer_pays(base_price=agreed.base_price, shipping=lot.shipping, pieces=pieces)
            got = seller_receives(base_price=agreed.base_price, pieces=pieces)
            console.print(
                f"[green]Agreed[/] at {agreed.base_price} a piece for {pieces} pieces, "
                f"inside both secret limits. Waiting for approval."
            )
            fee = paid.protection_fee
            console.print(f"Buyer pays {paid.total} (goods {paid.goods} + protection fee {fee})")
            console.print(
                f"Seller receives {got.net} (base {got.gross} - commission {got.commission})"
            )
        else:
            console.print(f"Ended: [yellow]{final}[/]")
