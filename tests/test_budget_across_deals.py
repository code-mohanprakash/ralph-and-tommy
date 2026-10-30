from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from fleek_agents.agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.config import Settings
from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Terms
from fleek_agents.domain.state import Actor, NegotiationState
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.rounds import send_card
from fleek_agents.orchestrator.run import run_negotiation
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.deals import accept, put_on_sale
from fleek_agents.store.events import EventLog
from fleek_agents.vault.budget import budget_check, committed
from fleek_agents.vault.mandate import BuyerMandate
from fleek_agents.vault.secret import SecretMoney
from tests.test_scripted import LOT, SELLER, WANT, limits

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
SETTINGS = Settings()
LOT_B = LOT.model_copy(update={"id": "lot-0002"})
LOTS = {LOT.id: LOT, LOT_B.id: LOT_B}


def market() -> tuple[EventLog, FakeClock]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    for lot in LOTS.values():
        put_on_sale(session, lot.id, bundles=1)
    return EventLog(session), FakeClock(T0)


def terms(price: int) -> Terms:
    return Terms(base_price=Pence(price), bundles=1, prepaid=False, ship_by=date(2026, 11, 23))


def test_open_offers_and_agreed_deals_count_and_nothing_else() -> None:
    log, clock = market()
    rules = SETTINGS.negotiation
    a = open_negotiation(log, buyer_id="buyer-0001", lot_id=LOT.id, clock=clock, rules=rules)
    b = open_negotiation(log, buyer_id="buyer-0001", lot_id=LOT_B.id, clock=clock, rules=rules)
    send_card(log, a, by=Actor.BUYER_AGENT, terms=terms(1000), clock=clock, rules=rules)
    send_card(log, b, by=Actor.BUYER_AGENT, terms=terms(1100), clock=clock, rules=rules)
    # 50 pieces x (base + £3.00 shipping) + the 2% fee (under the £20 cap)
    assert committed(log, "buyer-0001", LOTS) == Pence(66_300 + 71_400)
    send_card(log, b, by=Actor.SELLER_AGENT, terms=terms(1400), clock=clock, rules=rules)
    assert committed(log, "buyer-0001", LOTS) == Pence(
        66_300
    )  # b's offer is no longer on the table
    accept(log, a, lot_id=LOT.id, by=Actor.SELLER_AGENT, at=clock.now())
    assert committed(log, "buyer-0001", LOTS) == Pence(66_300)  # agreed deals still count
    assert committed(log, "buyer-0001", LOTS, leave_out=a) == Pence(0)


def test_a_buyer_can_t_end_up_with_two_deals_their_budget_only_covers_one() -> None:
    log, clock = market()
    rules = SETTINGS.negotiation
    buyer_limit, seller_limit = limits(max_pence=1600, floor_pence=950)
    one_deal = BuyerMandate(
        buyer_id="buyer-0001",
        max_per_piece=buyer_limit.max_per_piece,
        budget=SecretMoney(Pence(100_000)),
    )
    states = []
    for lot in (LOT, LOT_B):
        nid = open_negotiation(log, buyer_id="buyer-0001", lot_id=lot.id, clock=clock, rules=rules)
        state = run_negotiation(
            log,
            nid,
            lot=lot,
            seller=SELLER,
            want=WANT,
            bundles=1,
            buyer_limit=one_deal,
            seller_limit=seller_limit.__class__(
                seller_id="seller-01", lot_id=lot.id, floor_per_piece=seller_limit.floor_per_piece
            ),
            ralph=ScriptedRalph(),
            tommy=ScriptedTommy(),
            clock=clock,
            settings=SETTINGS,
            within_budget=budget_check(log, one_deal, nid, LOTS),
        )
        states.append((nid, state))
    assert states[0][1] is NegotiationState.PENDING_APPROVAL
    second, final = states[1]
    assert final is NegotiationState.NEEDS_HUMAN
    assert log.saved(second).escalated_because is EscalationReason.OVER_BUDGET
    assert committed(log, "buyer-0001", LOTS) <= Pence(100_000)


def test_no_budget_means_no_cross_deal_limit() -> None:
    log, _ = market()
    check = budget_check(log, limits(1600, 950)[0], "neg-0001", LOTS)
    assert check(Pence(10**9)) is True
