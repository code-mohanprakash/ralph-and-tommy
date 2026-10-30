from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from fleek_agents.domain.offers import OfferCard
from fleek_agents.domain.state import Actor, IllegalMove, Move, NegotiationState
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog

S, M, A = NegotiationState, Move, Actor
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def card(role: str, price: int, negotiation_id: str = "neg-0001") -> OfferCard:
    return OfferCard.model_validate(
        {
            "negotiation_id": negotiation_id,
            "round": 1,
            "from_role": role,
            "base_price": price,
            "bundles": 2,
            "prepaid": False,
            "ship_by": "2026-11-20",
            "expires_at": (T0 + timedelta(hours=48)).isoformat(),
        }
    )


@pytest.fixture
def log(tmp_path: Path) -> Iterator[EventLog]:
    engine = make_engine(f"sqlite:///{tmp_path / 'events.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield EventLog(session)


def test_moves_are_saved_in_order_and_read_back(log: EventLog) -> None:
    log.append("neg-0001", M.START, by=A.SYSTEM, at=T0)
    log.append("neg-0001", M.OFFER, by=A.BUYER_AGENT, at=T0, card=card("buyer", 1150))
    log.append("neg-0001", M.COUNTER, by=A.SELLER_AGENT, at=T0, card=card("seller", 1300))

    events = log.read("neg-0001")
    assert [e.seq for e in events] == [1, 2, 3]
    assert [(e.from_state, e.to_state) for e in events] == [
        (S.MATCHED, S.OPEN),
        (S.OPEN, S.OFFERED),
        (S.OFFERED, S.COUNTERED),
    ]
    assert events[1].card == card("buyer", 1150)
    assert events[0].at == T0  # the time zone survives the round trip
    assert log.state("neg-0001") is S.COUNTERED


def test_a_negotiation_with_no_events_is_matched(log: EventLog) -> None:
    assert log.state("neg-0009") is S.MATCHED
    assert log.read("neg-0009") == []


def test_an_illegal_move_is_refused_and_nothing_is_saved(log: EventLog) -> None:
    log.append("neg-0001", M.START, by=A.SYSTEM, at=T0)
    with pytest.raises(IllegalMove):
        log.append("neg-0001", M.APPROVE, by=A.BUYER_AGENT, at=T0)
    assert len(log.read("neg-0001")) == 1


@pytest.mark.parametrize(
    ("move", "actor", "the_card"),
    [
        (M.OFFER, A.BUYER_AGENT, None),  # an offer needs a card
        (M.OFFER, A.BUYER_AGENT, card("seller", 1150)),  # ...from the buyer's side
        (M.OFFER, A.BUYER_AGENT, card("buyer", 1150, "neg-0002")),  # ...for this negotiation
        (M.WALK_AWAY, A.BUYER_AGENT, card("buyer", 1150)),  # other moves carry no card
    ],
)
def test_a_card_must_fit_the_move(
    log: EventLog, move: Move, actor: Actor, the_card: OfferCard | None
) -> None:
    log.append("neg-0001", M.START, by=A.SYSTEM, at=T0)
    with pytest.raises(ValueError):
        log.append("neg-0001", move, by=actor, at=T0, card=the_card)
    assert len(log.read("neg-0001")) == 1


def test_negotiations_have_separate_histories(log: EventLog) -> None:
    log.append("neg-0001", M.START, by=A.SYSTEM, at=T0)
    log.append("neg-0002", M.FIND_IMPOSSIBLE, by=A.SYSTEM, at=T0)
    assert log.state("neg-0001") is S.OPEN
    assert log.state("neg-0002") is S.NO_DEAL_POSSIBLE
    assert log.read("neg-0002")[0].seq == 1
