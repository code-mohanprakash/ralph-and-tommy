from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from fleek_agents.config import NegotiationRules
from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Terms
from fleek_agents.domain.state import Actor, IllegalMove, Move, NegotiationState
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.controls import hand_over, stop
from fleek_agents.orchestrator.opening import CoolingDown, open_negotiation
from fleek_agents.orchestrator.rounds import send_card
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
RULES = NegotiationRules()
TERMS = Terms(base_price=Pence(1200), bundles=1, prepaid=False, ship_by=date(2026, 11, 20))


@pytest.fixture
def log() -> Iterator[EventLog]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield EventLog(session)


def opened(log: EventLog, clock: FakeClock) -> str:
    return open_negotiation(log, buyer_id="buyer-0001", lot_id="lot-0001", clock=clock, rules=RULES)


def test_a_person_can_stop_even_with_their_own_card_on_the_table(log: EventLog) -> None:
    clock = FakeClock(T0)
    n = opened(log, clock)
    send_card(log, n, by=Actor.BUYER_AGENT, terms=TERMS, clock=clock, rules=RULES)
    # Ralph couldn't walk away here (his offer is binding), but the buyer can stop him.
    with pytest.raises(IllegalMove):
        log.append(n, Move.WALK_AWAY, by=Actor.BUYER_AGENT, at=clock.now())
    stop(log, n, at=clock.now())
    assert log.state(n) is NegotiationState.STOPPED


def test_only_a_person_stops_and_not_after_agreement(log: EventLog) -> None:
    clock = FakeClock(T0)
    n = opened(log, clock)
    with pytest.raises(IllegalMove):
        log.append(n, Move.STOP, by=Actor.BUYER_AGENT, at=clock.now())
    send_card(log, n, by=Actor.BUYER_AGENT, terms=TERMS, clock=clock, rules=RULES)
    log.append(n, Move.ACCEPT, by=Actor.SELLER_AGENT, at=clock.now())
    with pytest.raises(IllegalMove):  # agreed: now it's approve or reject
        stop(log, n, at=clock.now())


def test_a_stopped_try_counts_as_a_failed_one(log: EventLog) -> None:
    clock = FakeClock(T0)
    stop(log, opened(log, clock), at=clock.now())
    with pytest.raises(CoolingDown):
        opened(log, clock)
    clock.advance(timedelta(hours=RULES.cooldown_hours, minutes=1))
    opened(log, clock)


def test_handing_over_goes_to_a_person_with_the_reason(log: EventLog) -> None:
    clock = FakeClock(T0)
    n = opened(log, clock)
    hand_over(log, n, at=clock.now())
    snap = log.saved(n)
    assert snap.state is NegotiationState.NEEDS_HUMAN
    assert snap.escalated_because is EscalationReason.ASKED_FOR_A_PERSON
