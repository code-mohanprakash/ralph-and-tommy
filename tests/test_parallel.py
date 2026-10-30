from collections import Counter
from pathlib import Path

from sqlalchemy.orm import Session

from fleek_agents.agents.base import Agent
from fleek_agents.agents.claude import ClaudeAgent
from fleek_agents.agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.config import Settings
from fleek_agents.domain.state import NegotiationState
from fleek_agents.llm.env import load_env_file
from fleek_agents.llm.replay import cassette_client
from fleek_agents.market.seed import generate_market
from fleek_agents.matching.funnel import bundles_for
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.run import Deal, link_buyer_deals, run_parallel
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog
from fleek_agents.store.market import load_market
from fleek_agents.vault.budget import budget_check, committed
from fleek_agents.vault.checks import can_accept
from fleek_agents.vault.mandate import BuyerMandate
from fleek_agents.vault.secret import SecretMoney
from fleek_agents.vault.seed import generate_mandates
from tests.test_scripted import T0

MARKET = generate_market(seed=2026)
SECRETS = generate_mandates(MARKET, seed=2026)
SELLERS = {s.id: s for s in MARKET.sellers}
LOTS = {lot.id: lot for lot in MARKET.lots}
WANT = MARKET.wants[0]  # buyer-0001: about 540 Tommy Hilfiger shirts
PICKED = ["lot-0248", "lot-0016", "lot-0389"]  # Ralph's three picks, from the #45 recording
SETTINGS = Settings()


def three_deals(ralph: Agent, buyer: BuyerMandate) -> tuple[EventLog, list[Deal]]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    load_market(session, MARKET)
    log, clock = EventLog(session), FakeClock(T0)
    deals = []
    for lot_id in PICKED:
        lot = LOTS[lot_id]
        nid = open_negotiation(
            log, buyer_id=WANT.buyer_id, lot_id=lot_id, clock=clock, rules=SETTINGS.negotiation
        )
        deals.append(
            Deal(
                nid,
                lot,
                SELLERS[lot.seller_id],
                WANT,
                bundles_for(WANT, lot),
                buyer,
                SECRETS.lots[lot_id],
                ralph,
                ScriptedTommy(),
                within_budget=budget_check(log, buyer, nid, LOTS),
            )
        )
    link_buyer_deals(log, deals)
    return log, deals


def test_the_picked_lots_are_the_ones_ralph_chose() -> None:
    assert all(LOTS[i].brand == "Tommy Hilfiger" for i in PICKED)


def test_three_scripted_deals_at_once_never_pass_the_budget() -> None:
    real = SECRETS.buyers[WANT.buyer_id]
    tight = BuyerMandate(
        buyer_id=real.buyer_id,
        max_per_piece=real.max_per_piece,
        budget=SecretMoney(real.max_per_piece.reveal().times(80)),
    )
    log, deals = three_deals(ScriptedRalph(), tight)
    states = run_parallel(log, deals, clock=FakeClock(T0), settings=SETTINGS)
    assert committed(log, WANT.buyer_id, LOTS) <= tight.budget.reveal()  # type: ignore[union-attr]
    assert set(states.values()) <= {
        NegotiationState.PENDING_APPROVAL,
        NegotiationState.NEEDS_HUMAN,
        NegotiationState.WALKED_AWAY,
    }


def test_live_claude_ralph_runs_three_deals_at_once() -> None:
    load_env_file(Path(__file__).parents[1] / ".env")
    buyer = SECRETS.buyers[WANT.buyer_id]
    ralph = ClaudeAgent(
        cassette_client(Path(__file__).parent / "cassettes" / "ralph_three_deals.jsonl"),
        model="claude-haiku-5-5",
        prompt="ralph",
    )
    log, deals = three_deals(ralph, buyer)
    states = run_parallel(log, deals, clock=FakeClock(T0), settings=SETTINGS)
    print("\n", Counter(states.values()))
    for deal in deals:
        cards = [e.card for e in log.read(deal.negotiation_id) if e.card is not None]
        print(
            f" {deal.lot.title}: " + ", ".join(f"{c.from_role[0]} {c.base_price}" for c in cards),
            "->",
            states[deal.negotiation_id],
        )
        agreed = log.saved(deal.negotiation_id).agreed
        if agreed is not None:
            assert can_accept(
                buyer,
                deal.seller_limit,
                base_price=agreed.base_price,
                shipping=deal.lot.shipping,
                pieces=agreed.bundles * deal.lot.pieces,
            )
    assert committed(log, WANT.buyer_id, LOTS) <= buyer.budget.reveal()  # type: ignore[union-attr]
    used = sum(t.calls for t in ralph.turns), sum(t.input_tokens for t in ralph.turns)
    print(f" {used[0]} calls, {used[1]} input tokens")
