"""The `fleek` command: run the marketplace from a terminal.

    fleek negotiate --mock    one buyer: match, negotiate with scripted agents, show the deal

It prints what each side would see, never a secret limit.
"""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy.orm import Session

from fleek_agents.agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.config import Settings, load_settings
from fleek_agents.domain.fees import buyer_pays, seller_receives
from fleek_agents.domain.models import Lot
from fleek_agents.domain.state import NegotiationState
from fleek_agents.llm.client import LiveClient, LLMClient
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


def _settings() -> Settings:
    """The numbers in market.toml, read fresh by every command, so editing the file changes them."""
    path = Path("market.toml")
    if not path.exists():
        Console().print("No market.toml here. Run fleek from the repository folder.")
        raise typer.Exit(code=2)
    return load_settings(path)


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

    settings = _settings()
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
    rows = safety_report(live=live, settings=_settings())
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
    rules = _settings().approval  # before opening the deals file, so a wrong folder makes no file
    session, lots = _session(db, seed)
    waiting = pending(EventLog(session), lots, rules)
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


@app.command()
def digest(
    db: Annotated[str, typer.Option(help="The deals file.")] = "fleek.db",
    seed: Annotated[int, typer.Option(help="Which seeded market.")] = 2026,
) -> None:
    """The account managers' call list: failed negotiations that came close, biggest first."""
    from fleek_agents.humans.digest import call_list

    rules = _settings().digest  # before opening the deals file, so a wrong folder makes no file
    session, lots = _session(db, seed)
    items = call_list(EventLog(session), lots, rules)
    console = Console()
    if not items:
        console.print("No near misses to call about.")
        return
    table = Table(
        "Negotiation", "Buyer", "Lot", "Ended", "Last offer", "Last counter", "Gap", "Worth"
    )
    for i in items:
        table.add_row(
            i.negotiation_id,
            i.buyer_id,
            i.lot_title,
            i.ended,
            str(i.last_offer),
            str(i.last_counter),
            f"{i.gap_pct}%",
            str(i.value),
        )
    console.print(table)


@app.command()
def summary(
    negotiation: Annotated[str, typer.Argument(help="e.g. neg-0001")],
    db: Annotated[str, typer.Option(help="The deals file.")] = "fleek.db",
    seed: Annotated[int, typer.Option(help="Which seeded market.")] = 2026,
) -> None:
    """The account manager's summary: what happened, where it stands, and what to do."""
    from fleek_agents.humans.handover import handover
    from fleek_agents.store.pairings import PairingRow

    settings = _settings()  # before opening the deals file, so a wrong folder makes no file
    session, lots = _session(db, seed)
    console = Console()
    if session.query(PairingRow).filter_by(negotiation_id=negotiation).first() is None:
        console.print(f"No negotiation called {negotiation} in {db}.")
        raise typer.Exit(code=2)
    h = handover(
        EventLog(session), negotiation, lots, approval=settings.approval, digest=settings.digest
    )
    if h is None:
        console.print(
            f"{negotiation}: no person needed. It ended {EventLog(session).state(negotiation)}."
        )
        return
    console.print(f"[bold]{negotiation}[/bold] · {h.buyer_id} · {h.lot_title}")
    console.print(f"Why you're seeing this: {h.why}")
    console.print("What happened:")
    for n, line in enumerate(h.happened, 1):
        console.print(f"  {n}. {line}")
    console.print(f"Where it stands: {h.stands}")
    console.print(f"What to do: {h.todo}")


class Agents(StrEnum):
    scripted = "scripted"
    haiku = "claude-haiku-5-5"
    sonnet = "claude-sonnet-5-5"


@app.command()
def simulate(
    agents: Annotated[
        Agents, typer.Option(help="Who negotiates, on both sides.")
    ] = Agents.scripted,
    buyers: Annotated[int, typer.Option(help="How many buyers, from buyer-0001.")] = 500,
    live: Annotated[
        bool, typer.Option("--live", help="Call Claude and record (needs the key).")
    ] = False,
    seed: Annotated[int, typer.Option(help="Which seeded market.")] = 2026,
) -> None:
    """Run many buyers through matching and negotiation, and measure the results."""
    from fleek_agents.agents.claude import ClaudeAgent
    from fleek_agents.evals.sim import simulate as run_simulation
    from fleek_agents.llm.budget import BudgetedClient, Ledger
    from fleek_agents.llm.env import load_env_file
    from fleek_agents.llm.replay import RecordingClient, ReplayClient

    settings = _settings()
    market = generate_market(seed=seed)
    secrets = generate_mandates(market, seed=seed)
    buyer_ids = [w.buyer_id for w in market.wants[:buyers]]
    if agents is Agents.scripted:
        summary = run_simulation(
            market,
            secrets,
            buyer_ids,
            agents="scripted",
            ralph=ScriptedRalph,
            tommy=ScriptedTommy,
            settings=settings,
        )
    else:
        recording = (
            Path(__file__).parent / "evals" / "recordings" / f"{agents.value}_{buyers}.jsonl"
        )
        if live:
            load_env_file()
            ledger = Ledger(cap_microcents=settings.spending.run_cap_cents * 1_000_000)
            client: LLMClient = RecordingClient(
                BudgetedClient(LiveClient(), ledger, settings.spending), recording
            )
        else:
            client = ReplayClient(recording)
        summary = run_simulation(
            market,
            secrets,
            buyer_ids,
            agents=agents.value,
            ralph=lambda: ClaudeAgent(client, model=agents.value, prompt="ralph"),
            tommy=lambda: ClaudeAgent(client, model=agents.value, prompt="tommy"),
            settings=settings,
        )
    line = summary.line()
    table = Table(*line)
    table.add_row(*line.values())
    Console().print(table)


@app.command()
def room(
    port: Annotated[int, typer.Option(help="Which port on this computer.")] = 8765,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the page in your browser.")
    ] = True,
    agents: Annotated[
        Agents, typer.Option(help="Who negotiates. Claude replays a recording unless --live.")
    ] = Agents.scripted,
    live: Annotated[
        bool, typer.Option("--live", help="Ask Claude now, any numbers (needs the key).")
    ] = False,
    record: Annotated[
        bool, typer.Option("--record", help="Record Claude on every scenario, then stop.")
    ] = False,
) -> None:
    """The Deal Room: one negotiation, run by the real code, shown step by step in a browser."""
    import webbrowser

    from fleek_agents.llm.env import load_env_file
    from fleek_agents.room import agents as who
    from fleek_agents.room.server import Room, make_server

    console = Console()
    settings = _settings()
    model = agents.value
    name = who.MODEL_NAMES.get(model, model)
    if agents is Agents.scripted:
        if live or record:
            console.print("--live and --record are for Claude: add --agents claude-haiku-5-5.")
            raise typer.Exit(code=2)
        desk = Room(settings, who.scripted())
    elif record:
        load_env_file()
        for key, run in who.record(model, settings):
            console.print(f"{key}: {run.final or 'no match'}")
        console.print(f"Recorded {name} on every scenario in {who.RECORDINGS}.")
        return
    elif live:
        load_env_file()
        desk = Room(settings, who.live(model, settings), f"{name}, live", scripted=False)
    else:
        desk = Room(settings, who.replayed(model), f"{name}, replayed from a recording", False)
    try:
        server = make_server(desk, port)
    except OSError:
        console.print(f"Port {port} is busy. Try another: fleek room --port {port + 1}")
        raise typer.Exit(code=2) from None
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    console.print(f"The Deal Room is open at {url}  (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("Stopped.")
    finally:
        server.server_close()


@app.command()
def export(
    out: Annotated[str, typer.Option(help="Where to write the run, e.g. viewer/runs/run.json.")],
    db: Annotated[str, typer.Option(help="The deals file.")] = "fleek.db",
    title: Annotated[str, typer.Option(help="A name for the run.")] = "A run",
    seed: Annotated[int, typer.Option(help="Which seeded market.")] = 2026,
) -> None:
    """Write every negotiation in the deals file to a JSON run the Deal Room can play."""
    from fleek_agents.store.pairings import PairingRow
    from fleek_agents.trace.export import export_run

    session, lots = _session(db, seed)
    ids = [
        r.negotiation_id
        for r in session.query(PairingRow).order_by(PairingRow.id)
        if r.negotiation_id
    ]
    trace = export_run(EventLog(session), ids, lots, title=title)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    Console().print(f"Wrote {len(ids)} negotiation(s) to {out}.")
