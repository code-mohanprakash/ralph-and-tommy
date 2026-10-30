from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.state import Actor, Move, NegotiationState
from fleek_agents.harness.escalation import count_escalations, escalate_if_needed
from fleek_agents.harness.loop import Outcome, Tool, TurnResult, take_turn
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog
from tests.fakes import FakeClient, message, text
from tests.test_tool_loop import NoInput

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
R = EscalationReason


@pytest.fixture
def log() -> Iterator[EventLog]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield EventLog(session)


def opened(log: EventLog, nid: str = "neg-0001") -> str:
    log.append(nid, Move.START, by=Actor.SYSTEM, at=T0)
    return nid


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (Outcome.REFUSED, R.MODEL_REFUSED),
        (Outcome.NEEDS_HUMAN, R.TOO_MANY_CORRECTIONS),
        (Outcome.SPEND_CAP, R.SPEND_CAP),
    ],
)
def test_a_turn_with_no_valid_action_goes_to_a_person_with_its_reason(
    log: EventLog, outcome: Outcome, reason: EscalationReason
) -> None:
    nid = opened(log)
    assert escalate_if_needed(log, nid, TurnResult(outcome=outcome), at=T0) is reason
    assert log.state(nid) is NegotiationState.NEEDS_HUMAN
    assert log.read(nid)[-1].reason is reason
    assert log.saved(nid).escalated_because is reason


def test_a_turn_with_an_action_carries_on(log: EventLog) -> None:
    nid = opened(log)
    assert escalate_if_needed(log, nid, TurnResult(outcome=Outcome.ACTION), at=T0) is None
    assert log.state(nid) is NegotiationState.OPEN


def test_a_real_refusal_from_the_model_ends_up_with_a_person(log: EventLog) -> None:
    nid = opened(log)
    walk = Tool(name="walk_away", description="Leave.", input_model=NoInput, is_action=True)
    turn = take_turn(
        FakeClient(message(text(""), stop="refusal")),
        model="claude-haiku-5-5",
        system="s",
        prompt="p",
        tools=[walk],
    )
    escalate_if_needed(log, nid, turn, at=T0)
    assert log.read(nid)[-1].reason is R.MODEL_REFUSED


def test_an_escalation_needs_a_reason_and_other_moves_can_t_have_one(log: EventLog) -> None:
    nid = opened(log)
    with pytest.raises(ValidationError):
        log.append(nid, Move.ESCALATE, by=Actor.SYSTEM, at=T0)
    with pytest.raises(ValidationError):
        log.append(nid, Move.WALK_AWAY, by=Actor.BUYER_AGENT, at=T0, reason=R.SPEND_CAP)


def test_escalations_are_counted_by_reason(log: EventLog) -> None:
    for n, outcome in enumerate([Outcome.REFUSED, Outcome.REFUSED, Outcome.SPEND_CAP], start=1):
        nid = opened(log, f"neg-{n:04d}")
        escalate_if_needed(log, nid, TurnResult(outcome=outcome), at=T0)
    opened(log, "neg-0004")  # not escalated
    counts = count_escalations(log, [f"neg-{n:04d}" for n in range(1, 5)])
    assert counts == {R.MODEL_REFUSED: 2, R.SPEND_CAP: 1}
