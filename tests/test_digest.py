from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from fleek_agents.config import DigestRules, Settings
from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.models import Lot
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Terms
from fleek_agents.domain.state import Actor, Move, NegotiationState
from fleek_agents.humans.digest import call_list
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.rounds import send_card
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.deals import put_on_sale
from fleek_agents.store.events import EventLog
from tests.test_scripted import LOT

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
SETTINGS = Settings()
RULES = DigestRules()


@pytest.fixture
def log() -> Iterator[EventLog]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield EventLog(session)


def haggle(log: EventLog, n: int, offer: int, counter: int, pieces_lot: int = 50) -> str:
    lot_id = f"lot-{n:04d}"
    clock = FakeClock(T0)
    put_on_sale(log.session, lot_id, bundles=1)
    nid = open_negotiation(
        log, buyer_id=f"buyer-{n:04d}", lot_id=lot_id, clock=clock, rules=SETTINGS.negotiation
    )
    for who, price in ((Actor.BUYER_AGENT, offer), (Actor.SELLER_AGENT, counter)):
        terms = Terms(base_price=Pence(price), bundles=1, prepaid=False, ship_by=date(2026, 11, 23))
        send_card(log, nid, by=who, terms=terms, clock=clock, rules=SETTINGS.negotiation)
    return nid


def lots(n: int) -> dict[str, Lot]:
    return {f"lot-{i:04d}": LOT.model_copy(update={"id": f"lot-{i:04d}"}) for i in range(1, n + 1)}


def test_near_misses_make_the_list_and_far_ones_don_t(log: EventLog) -> None:
    close = haggle(log, 1, offer=1150, counter=1200)  # about 4% apart
    far = haggle(log, 2, offer=800, counter=1200)  # a third apart
    for nid in (close, far):
        log.append(nid, Move.WALK_AWAY, by=Actor.BUYER_AGENT, at=T0)
    items = call_list(log, lots(2), RULES)
    assert [i.negotiation_id for i in items] == [close]
    assert items[0].gap_pct == 4 and items[0].ended == "walked_away"


def test_bigger_deals_come_first(log: EventLog) -> None:
    small = haggle(log, 1, offer=1150, counter=1200)
    big = haggle(log, 2, offer=2300, counter=2400)
    for nid in (small, big):
        log.append(nid, Move.WALK_AWAY, by=Actor.BUYER_AGENT, at=T0)
    assert [i.negotiation_id for i in call_list(log, lots(2), RULES)] == [big, small]


def test_a_deal_handed_to_a_person_says_why(log: EventLog) -> None:
    nid = haggle(log, 1, offer=1150, counter=1200)
    log.append(nid, Move.ESCALATE, by=Actor.SYSTEM, at=T0, reason=EscalationReason.MODEL_REFUSED)
    item = call_list(log, lots(1), RULES)[0]
    assert item.ended == "needs_human: model_refused"


def test_live_and_agreed_deals_aren_t_near_misses(log: EventLog) -> None:
    haggle(log, 1, offer=1150, counter=1200)  # still countered, not over
    assert log.state("neg-0001") is NegotiationState.COUNTERED
    assert call_list(log, lots(1), RULES) == []


def test_the_list_holds_only_what_both_sides_saw() -> None:
    fields = {
        "negotiation_id",
        "buyer_id",
        "lot_title",
        "ended",
        "last_offer",
        "last_counter",
        "gap_pct",
        "value",
    }
    from dataclasses import fields as dc_fields

    from fleek_agents.humans.digest import CallItem

    assert {f.name for f in dc_fields(CallItem)} == fields
