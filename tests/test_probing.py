from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from fleek_agents.config import NegotiationRules
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Terms
from fleek_agents.domain.state import Actor, IllegalMove, Move, NegotiationState
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import AlreadyNegotiating, CoolingDown, open_negotiation
from fleek_agents.orchestrator.rounds import BackwardsConcession, send_card
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog

A, S = Actor, NegotiationState
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
RULES = NegotiationRules()


def terms(price: int) -> Terms:
    return Terms(base_price=Pence(price), bundles=1, prepaid=False, ship_by=date(2026, 11, 20))


@pytest.fixture
def log() -> Iterator[EventLog]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield EventLog(session)


def test_a_probing_bot_is_stopped_at_every_turn(log: EventLog) -> None:
    clock = FakeClock(T0)
    first = open_negotiation(
        log, buyer_id="buyer-0666", lot_id="lot-0001", clock=clock, rules=RULES
    )
    send_card(log, first, by=A.BUYER_AGENT, terms=terms(500), clock=clock, rules=RULES)

    # 1. Leave with the low offer still on the table, to try another? Offers are binding.
    with pytest.raises(IllegalMove):
        log.append(first, Move.WALK_AWAY, by=A.BUYER_AGENT, at=clock.now())

    # 2. Open a second negotiation on the same lot alongside? One at a time.
    with pytest.raises(AlreadyNegotiating):
        open_negotiation(log, buyer_id="buyer-0666", lot_id="lot-0001", clock=clock, rules=RULES)

    # The seller counters. 3. Drop the offer to see if the counter follows? One way only.
    send_card(log, first, by=A.SELLER_AGENT, terms=terms(1400), clock=clock, rules=RULES)
    with pytest.raises(BackwardsConcession):
        send_card(log, first, by=A.BUYER_AGENT, terms=terms(400), clock=clock, rules=RULES)

    # 4. Walk away (allowed now: it's the bot's turn) and start again straight away? Cooldown.
    log.append(first, Move.WALK_AWAY, by=A.BUYER_AGENT, at=clock.now())
    clock.advance(timedelta(hours=23, minutes=59))
    with pytest.raises(CoolingDown):
        open_negotiation(log, buyer_id="buyer-0666", lot_id="lot-0001", clock=clock, rules=RULES)

    # After 24 hours it may try again, as anyone could.
    clock.advance(timedelta(minutes=1))
    again = open_negotiation(
        log, buyer_id="buyer-0666", lot_id="lot-0001", clock=clock, rules=RULES
    )
    assert again != first and log.state(again) is S.OPEN


def test_the_cooldown_is_per_buyer_and_lot(log: EventLog) -> None:
    clock = FakeClock(T0)
    first = open_negotiation(
        log, buyer_id="buyer-0001", lot_id="lot-0001", clock=clock, rules=RULES
    )
    log.append(first, Move.WALK_AWAY, by=A.BUYER_AGENT, at=clock.now())
    open_negotiation(
        log, buyer_id="buyer-0001", lot_id="lot-0002", clock=clock, rules=RULES
    )  # other lot
    open_negotiation(
        log, buyer_id="buyer-0002", lot_id="lot-0001", clock=clock, rules=RULES
    )  # other buyer


def test_losing_a_lot_to_someone_else_is_not_a_failed_probe(log: EventLog) -> None:
    clock = FakeClock(T0)
    first = open_negotiation(
        log, buyer_id="buyer-0001", lot_id="lot-0001", clock=clock, rules=RULES
    )
    log.append(first, Move.LOSE_LOT, by=A.SYSTEM, at=clock.now())
    open_negotiation(log, buyer_id="buyer-0001", lot_id="lot-0001", clock=clock, rules=RULES)


def test_negotiation_ids_are_new_each_time(log: EventLog) -> None:
    clock = FakeClock(T0)
    ids = {
        open_negotiation(
            log, buyer_id=f"buyer-{n:04d}", lot_id="lot-0001", clock=clock, rules=RULES
        )
        for n in range(1, 6)
    }
    assert len(ids) == 5
