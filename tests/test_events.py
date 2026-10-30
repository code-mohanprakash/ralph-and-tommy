import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleek_agents.domain.events import CARD_FROM
from fleek_agents.domain.offers import OfferCard
from fleek_agents.domain.replay import replay
from fleek_agents.domain.state import ALLOWED, Actor, IllegalMove, Move, NegotiationState
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


def test_the_database_refuses_to_edit_an_event(log: EventLog) -> None:
    log.append("neg-0001", M.START, by=A.SYSTEM, at=T0)
    with pytest.raises(IntegrityError, match="append-only"):
        log._session.execute(text("UPDATE events SET to_state = 'closed'"))
    log._session.rollback()
    assert log.state("neg-0001") is S.OPEN


def test_the_database_refuses_to_delete_an_event(log: EventLog) -> None:
    log.append("neg-0001", M.START, by=A.SYSTEM, at=T0)
    with pytest.raises(IntegrityError, match="append-only"):
        log._session.execute(text("DELETE FROM events"))
    log._session.rollback()
    assert len(log.read("neg-0001")) == 1


def test_two_writers_cant_both_save_the_same_event_number(log: EventLog) -> None:
    log.append("neg-0001", M.START, by=A.SYSTEM, at=T0)
    with pytest.raises(IntegrityError):
        log._session.execute(
            text(
                "INSERT INTO events (negotiation_id, seq, move, to_state, data) "
                "VALUES ('neg-0001', 1, 'start', 'open', '{}')"
            )
        )
    log._session.rollback()


def test_the_saved_state_matches_a_replay_of_the_log(log: EventLog) -> None:
    log.append("neg-0001", M.START, by=A.SYSTEM, at=T0)
    log.append("neg-0001", M.OFFER, by=A.BUYER_AGENT, at=T0, card=card("buyer", 1150))
    log.append("neg-0001", M.COUNTER, by=A.SELLER_AGENT, at=T0, card=card("seller", 1300))
    saved = log.saved("neg-0001")
    assert saved.state is S.COUNTERED
    assert saved.last_counter == card("seller", 1300)
    assert saved == replay("neg-0001", log.read("neg-0001"))


def test_an_unknown_negotiation_has_a_fresh_snapshot(log: EventLog) -> None:
    assert log.saved("neg-0009") == replay("neg-0009", [])


def _random_walk(log: EventLog, negotiation_id: str, rng: random.Random) -> None:
    for step in range(rng.randint(1, 12)):
        state = log.state(negotiation_id)
        options = [
            (move, actor)
            for (s, move), (_, actors) in ALLOWED.items()
            if s is state
            for actor in sorted(actors)
        ]
        if not options:
            return  # an ending
        move, actor = rng.choice(options)
        role = CARD_FROM.get(move)
        the_card = card(role.value, rng.randint(500, 2000), negotiation_id) if role else None
        log.append(negotiation_id, move, by=actor, at=T0 + timedelta(minutes=step), card=the_card)


def test_saved_state_matches_replay_after_300_random_negotiations(log: EventLog) -> None:
    rng = random.Random(30)  # fixed seed: the same 300 negotiations every run
    for n in range(300):
        negotiation_id = f"neg-{n:04d}"
        _random_walk(log, negotiation_id, rng)
        assert log.saved(negotiation_id) == replay(negotiation_id, log.read(negotiation_id))


def test_when_two_writers_race_the_loser_saves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as one, Session(engine) as two:
        first, second = EventLog(one), EventLog(two)
        first.append("neg-0001", M.START, by=A.SYSTEM, at=T0)
        # The race: the second writer reads the state, then the first writer saves event 2
        # before the second one writes. The second is now acting on an out-of-date snapshot.
        stale = second.saved("neg-0001")
        first.append("neg-0001", M.OFFER, by=A.BUYER_AGENT, at=T0, card=card("buyer", 1150))
        monkeypatch.setattr(second, "saved", lambda _negotiation_id: stale)
        with pytest.raises(IntegrityError):  # it also tries to save event 2
            second.append("neg-0001", M.WALK_AWAY, by=A.SELLER_AGENT, at=T0)
        two.rollback()
        monkeypatch.undo()
        assert second.state("neg-0001") is S.OFFERED  # the first writer's move stands
        assert second.saved("neg-0001") == replay("neg-0001", second.read("neg-0001"))
