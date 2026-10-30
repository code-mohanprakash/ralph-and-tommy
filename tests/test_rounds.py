import time
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from fleek_agents.config import NegotiationRules
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Terms
from fleek_agents.domain.state import Actor, Move, NegotiationState
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.rounds import (
    BackwardsConcession,
    RoundLimitReached,
    expire_due,
    send_card,
)
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog

S, M, A = NegotiationState, Move, Actor
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
RULES = NegotiationRules()  # 6 rounds, 48 hours
TERMS = Terms(base_price=Pence(1200), bundles=1, prepaid=False, ship_by=date(2026, 11, 20))


@pytest.fixture
def log() -> Iterator[EventLog]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield EventLog(session)


def started(log: EventLog, clock: FakeClock, negotiation_id: str = "neg-0001") -> None:
    log.append(negotiation_id, M.START, by=A.SYSTEM, at=clock.now())


def test_the_harness_numbers_each_card_and_sets_its_48_hour_expiry(log: EventLog) -> None:
    clock = FakeClock(T0)
    started(log, clock)
    send_card(log, "neg-0001", by=A.BUYER_AGENT, terms=TERMS, clock=clock, rules=RULES)
    clock.advance(timedelta(hours=3))
    send_card(log, "neg-0001", by=A.SELLER_AGENT, terms=TERMS, clock=clock, rules=RULES)

    offer, counter = log.saved("neg-0001").last_offer, log.saved("neg-0001").last_counter
    assert offer is not None and counter is not None
    assert (offer.round, counter.round) == (1, 2)
    assert counter.expires_at == T0 + timedelta(hours=3 + 48)
    assert log.state("neg-0001") is S.COUNTERED


def test_a_seventh_card_is_refused_but_the_sixth_can_still_be_accepted(log: EventLog) -> None:
    clock = FakeClock(T0)
    started(log, clock)
    for n in range(6):
        side = A.BUYER_AGENT if n % 2 == 0 else A.SELLER_AGENT
        send_card(log, "neg-0001", by=side, terms=TERMS, clock=clock, rules=RULES)
    before = log.saved("neg-0001")
    with pytest.raises(RoundLimitReached):
        send_card(log, "neg-0001", by=A.BUYER_AGENT, terms=TERMS, clock=clock, rules=RULES)
    assert log.saved("neg-0001") == before  # nothing saved
    log.append("neg-0001", M.ACCEPT, by=A.BUYER_AGENT, at=clock.now())
    assert log.state("neg-0001") is S.PENDING_APPROVAL


def test_a_card_expires_exactly_48_hours_after_it_was_sent(log: EventLog) -> None:
    started_at = time.perf_counter()
    clock = FakeClock(T0)
    started(log, clock)
    send_card(log, "neg-0001", by=A.BUYER_AGENT, terms=TERMS, clock=clock, rules=RULES)

    clock.advance(timedelta(hours=47, minutes=59))
    assert expire_due(log, ["neg-0001"], clock=clock, rules=RULES) == []
    clock.advance(timedelta(minutes=1))
    assert expire_due(log, ["neg-0001"], clock=clock, rules=RULES) == ["neg-0001"]
    assert log.state("neg-0001") is S.EXPIRED
    assert time.perf_counter() - started_at < 1  # two days, skipped in under a second


def test_an_open_negotiation_with_no_offer_expires_48_hours_after_it_started(log: EventLog) -> None:
    clock = FakeClock(T0)
    started(log, clock)
    clock.advance(timedelta(hours=48))
    assert expire_due(log, ["neg-0001"], clock=clock, rules=RULES) == ["neg-0001"]


def test_a_deal_waiting_for_approval_expires_too(log: EventLog) -> None:
    clock = FakeClock(T0)
    started(log, clock)
    send_card(log, "neg-0001", by=A.BUYER_AGENT, terms=TERMS, clock=clock, rules=RULES)
    log.append("neg-0001", M.ACCEPT, by=A.SELLER_AGENT, at=clock.now())
    clock.advance(timedelta(hours=48))
    assert expire_due(log, ["neg-0001"], clock=clock, rules=RULES) == ["neg-0001"]


def test_an_ended_negotiation_is_left_alone(log: EventLog) -> None:
    clock = FakeClock(T0)
    started(log, clock)
    log.append("neg-0001", M.WALK_AWAY, by=A.BUYER_AGENT, at=clock.now())
    clock.advance(timedelta(days=30))
    assert expire_due(log, ["neg-0001"], clock=clock, rules=RULES) == []


def test_only_agents_send_cards(log: EventLog) -> None:
    clock = FakeClock(T0)
    started(log, clock)
    with pytest.raises(ValueError):
        send_card(log, "neg-0001", by=A.SYSTEM, terms=TERMS, clock=clock, rules=RULES)


def test_a_fake_clock_only_moves_when_told() -> None:
    clock = FakeClock(T0)
    assert clock.now() == T0
    clock.advance(timedelta(seconds=5))
    assert clock.now() == T0 + timedelta(seconds=5)
    with pytest.raises(ValueError):
        clock.advance(timedelta(seconds=-1))


def terms(price: int) -> Terms:
    return TERMS.model_copy(update={"base_price": Pence(price)})


def test_a_buyer_can_only_raise_their_offer(log: EventLog) -> None:
    clock = FakeClock(T0)
    started(log, clock)
    send_card(log, "neg-0001", by=A.BUYER_AGENT, terms=terms(1000), clock=clock, rules=RULES)
    send_card(log, "neg-0001", by=A.SELLER_AGENT, terms=terms(1400), clock=clock, rules=RULES)
    before = log.saved("neg-0001")
    with pytest.raises(BackwardsConcession):
        send_card(log, "neg-0001", by=A.BUYER_AGENT, terms=terms(999), clock=clock, rules=RULES)
    assert log.saved("neg-0001") == before
    send_card(
        log, "neg-0001", by=A.BUYER_AGENT, terms=terms(1000), clock=clock, rules=RULES
    )  # same is fine


def test_a_seller_can_only_lower_their_counter(log: EventLog) -> None:
    clock = FakeClock(T0)
    started(log, clock)
    send_card(log, "neg-0001", by=A.BUYER_AGENT, terms=terms(1000), clock=clock, rules=RULES)
    send_card(log, "neg-0001", by=A.SELLER_AGENT, terms=terms(1400), clock=clock, rules=RULES)
    send_card(log, "neg-0001", by=A.BUYER_AGENT, terms=terms(1100), clock=clock, rules=RULES)
    with pytest.raises(BackwardsConcession):
        send_card(log, "neg-0001", by=A.SELLER_AGENT, terms=terms(1401), clock=clock, rules=RULES)
