from collections import Counter
from dataclasses import fields
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from fleek_agents.agents.base import Accept, View
from fleek_agents.agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.config import Settings
from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.models import Lot, Seller, Want
from fleek_agents.domain.money import Pence
from fleek_agents.domain.state import NegotiationState
from fleek_agents.market.seed import generate_market
from fleek_agents.matching.funnel import bundles_for, possible_deals
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.run import run_negotiation
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.deals import put_on_sale
from fleek_agents.store.events import EventLog
from fleek_agents.store.market import load_market
from fleek_agents.vault.checks import can_accept
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate
from fleek_agents.vault.secret import SecretMoney
from fleek_agents.vault.seed import generate_mandates

S = NegotiationState
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
SETTINGS = Settings()
MARKET = generate_market(seed=2026)
SECRETS = generate_mandates(MARKET, seed=2026)
SELLERS = {s.id: s for s in MARKET.sellers}
LOTS = {lot.id: lot for lot in MARKET.lots}

LOT = Lot.model_validate(
    {
        "id": "lot-0001",
        "seller_id": "seller-01",
        "title": "Levi's 501 jeans, grade A, 50 pcs",
        "brand": "Levi's",
        "category": "jeans",
        "grade": "A",
        "listing_type": "exact",
        "pieces": 50,
        "available": 1,
        "base_price": 1400,
        "shipping": 300,
        "description": "Washed and sorted.",
    }
)
SELLER = Seller(
    id="seller-01", name="Karachi Denim", country="PK", quality_score=4.5, dispatch_days=2
)
WANT = Want(buyer_id="buyer-0001", category="jeans", grades=("A",), pieces=50, text="Levi's 501s")


def limits(max_pence: int, floor_pence: int) -> tuple[BuyerMandate, SellerMandate]:
    return (
        BuyerMandate(buyer_id="buyer-0001", max_per_piece=SecretMoney(Pence(max_pence))),
        SellerMandate(
            seller_id="seller-01",
            lot_id="lot-0001",
            floor_per_piece=SecretMoney(Pence(floor_pence)),
        ),
    )


def run(max_pence: int, floor_pence: int) -> tuple[EventLog, str, NegotiationState]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    log, clock = EventLog(session), FakeClock(T0)
    put_on_sale(session, LOT.id, bundles=1)
    nid = open_negotiation(
        log, buyer_id="buyer-0001", lot_id=LOT.id, clock=clock, rules=SETTINGS.negotiation
    )
    b, s = limits(max_pence, floor_pence)
    state = run_negotiation(
        log,
        nid,
        lot=LOT,
        seller=SELLER,
        want=WANT,
        bundles=1,
        buyer_limit=b,
        seller_limit=s,
        ralph=ScriptedRalph(),
        tommy=ScriptedTommy(),
        clock=clock,
        settings=SETTINGS,
    )
    return log, nid, state


def test_a_scripted_deal_closes_inside_both_limits() -> None:
    # Buyer will pay up to £16.00 delivered; seller needs £9.50 net (about £11.18 base).
    log, nid, state = run(max_pence=1600, floor_pence=950)
    assert state is S.PENDING_APPROVAL
    events = log.read(nid)
    agreed = [e.card for e in events if e.card is not None][-1]
    b, s = limits(1600, 950)
    assert can_accept(b, s, base_price=agreed.base_price, shipping=LOT.shipping, pieces=50)
    assert len([e for e in events if e.card]) >= 2  # they actually negotiated


def test_a_deal_with_no_room_never_accepts() -> None:
    log, nid, state = run(max_pence=1000, floor_pence=1100)  # no price works for both
    assert state in {S.WALKED_AWAY, S.NEEDS_HUMAN}
    assert all(e.move != "accept" for e in log.read(nid))


def test_the_same_run_gives_the_same_events() -> None:
    first, again = run(1600, 950), run(1600, 950)
    assert first[0].read(first[1]) == again[0].read(again[1])


def test_an_agent_s_view_holds_no_secret_field() -> None:
    assert {f.name for f in fields(View)} == {
        "lot",
        "want",
        "bundles",
        "list_price",
        "history",
        "rounds_left",
        "band",
        "today",
    }


def test_scripted_agents_on_the_seeded_market_never_break_a_limit() -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    load_market(session, MARKET)
    log, clock = EventLog(session), FakeClock(T0)
    outcomes: Counter[str] = Counter()
    for want in MARKET.wants[:80]:
        candidates = possible_deals(session, MARKET, SECRETS, want)
        if not candidates:
            continue
        lot = candidates[0].lot
        nid = open_negotiation(
            log, buyer_id=want.buyer_id, lot_id=lot.id, clock=clock, rules=SETTINGS.negotiation
        )
        state = run_negotiation(
            log,
            nid,
            lot=lot,
            seller=SELLERS[lot.seller_id],
            want=want,
            bundles=bundles_for(want, lot),
            buyer_limit=SECRETS.buyers[want.buyer_id],
            seller_limit=SECRETS.lots[lot.id],
            ralph=ScriptedRalph(),
            tommy=ScriptedTommy(),
            clock=clock,
            settings=SETTINGS,
        )
        outcomes[state] += 1
        if state is S.PENDING_APPROVAL:
            agreed = [e.card for e in log.read(nid) if e.card is not None][-1]
            assert can_accept(
                SECRETS.buyers[want.buyer_id],
                SECRETS.lots[lot.id],
                base_price=agreed.base_price,
                shipping=lot.shipping,
                pieces=agreed.bundles * lot.pieces,
            )
    print("\nscripted outcomes:", dict(outcomes))
    assert outcomes[S.PENDING_APPROVAL] > 0
    assert S.NEEDS_HUMAN not in outcomes  # no agent tried to accept outside a limit


class RecklessTommy:
    """Accepts whatever is offered, limits or not: what a confused or tricked AI might do."""

    def decide(self, view: View) -> Accept:
        return Accept()


def test_the_harness_refuses_an_accept_outside_a_limit() -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    log, clock = EventLog(session), FakeClock(T0)
    put_on_sale(session, LOT.id, bundles=1)
    nid = open_negotiation(
        log, buyer_id="buyer-0001", lot_id=LOT.id, clock=clock, rules=SETTINGS.negotiation
    )
    b, s = limits(max_pence=1600, floor_pence=1300)  # Ralph opens at 80% of list: below the floor
    state = run_negotiation(
        log,
        nid,
        lot=LOT,
        seller=SELLER,
        want=WANT,
        bundles=1,
        buyer_limit=b,
        seller_limit=s,
        ralph=ScriptedRalph(),
        tommy=RecklessTommy(),
        clock=clock,
        settings=SETTINGS,
    )
    assert state is S.NEEDS_HUMAN  # handed to a person, not sold below the floor
    assert log.saved(nid).escalated_because is EscalationReason.ACCEPT_OUTSIDE_LIMIT
    assert all(e.move != "accept" for e in log.read(nid))
