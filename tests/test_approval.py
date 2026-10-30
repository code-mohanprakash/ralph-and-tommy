from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from fleek_agents.config import ApprovalRules, Settings
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Terms
from fleek_agents.domain.state import Actor, IllegalMove, NegotiationState
from fleek_agents.orchestrator.approval import approve, needs_person, pending, reject, settle
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.rounds import send_card
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.deals import accept, put_on_sale, stock_left
from fleek_agents.store.events import EventLog
from tests.test_scripted import LOT

S = NegotiationState
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
RULES = ApprovalRules()
SETTINGS = Settings()
LOTS = {LOT.id: LOT}


@pytest.mark.parametrize(
    ("total", "closed", "person"),
    [(149_999, 3, False), (150_000, 3, True), (50_000, 2, True), (50_000, 0, True)],
)
def test_big_deals_and_a_buyer_s_first_three_wait_for_a_person(
    total: int, closed: int, person: bool
) -> None:
    assert needs_person(Pence(total), closed_before=closed, rules=RULES) is person


@pytest.fixture
def log() -> Iterator[EventLog]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield EventLog(session)


def agreed(log: EventLog, lot_id: str = LOT.id, price: int = 1200) -> str:
    clock = FakeClock(T0)
    put_on_sale(log.session, lot_id, bundles=1)
    nid = open_negotiation(
        log, buyer_id="buyer-0001", lot_id=lot_id, clock=clock, rules=SETTINGS.negotiation
    )
    terms = Terms(base_price=Pence(price), bundles=1, prepaid=False, ship_by=date(2026, 11, 23))
    send_card(log, nid, by=Actor.BUYER_AGENT, terms=terms, clock=clock, rules=SETTINGS.negotiation)
    accept(log, nid, lot_id=lot_id, by=Actor.SELLER_AGENT, at=clock.now())
    return nid


def test_a_buyer_s_first_deal_waits_and_shows_up_as_pending(log: EventLog) -> None:
    nid = agreed(log)
    assert settle(log, nid, lots=LOTS, rules=RULES, at=T0) is S.PENDING_APPROVAL
    waiting = pending(log, LOTS, RULES)
    assert [w.negotiation_id for w in waiting] == [nid]
    assert waiting[0].why == "one of the buyer's first 3 deals"


def test_a_small_deal_after_three_closed_is_approved_automatically(log: EventLog) -> None:
    lots = {f"lot-{n:04d}": LOT.model_copy(update={"id": f"lot-{n:04d}"}) for n in range(1, 5)}
    for lot_id in list(lots)[:3]:
        approve(log, agreed(log, lot_id), at=T0)
    fourth = agreed(log, "lot-0004")
    assert settle(log, fourth, lots=lots, rules=RULES, at=T0) is S.CLOSED
    assert log.read(fourth)[-1].by is Actor.SYSTEM  # the record says the rule approved it


def test_a_person_approves_and_the_deal_closes(log: EventLog) -> None:
    nid = agreed(log)
    approve(log, nid, at=T0)
    assert log.state(nid) is S.CLOSED
    assert log.read(nid)[-1].by is Actor.HUMAN


def test_a_rejection_puts_the_stock_back_on_sale(log: EventLog) -> None:
    nid = agreed(log)
    assert stock_left(log.session, LOT.id) == 0
    reject(log, nid, at=T0)
    assert log.state(nid) is S.REJECTED_BY_HUMAN
    assert stock_left(log.session, LOT.id) == 1


def test_only_a_waiting_deal_can_be_approved(log: EventLog) -> None:
    nid = agreed(log)
    approve(log, nid, at=T0)
    with pytest.raises(IllegalMove):
        approve(log, nid, at=T0)
