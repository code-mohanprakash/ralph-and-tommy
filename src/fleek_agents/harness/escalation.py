"""When a turn ends without a valid action, the negotiation goes to a person, with the reason.

No guessing on the agent's behalf: a refusal, a model that can't produce a valid action after
its corrections, or a spend cap all stop the negotiation and say why. The reasons are counted, so
the account managers can see how often each happens.
"""

from collections import Counter
from collections.abc import Iterable
from datetime import datetime

from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.state import Actor, Move
from fleek_agents.harness.loop import Outcome, TurnResult
from fleek_agents.store.events import EventLog

REASONS = {
    Outcome.REFUSED: EscalationReason.MODEL_REFUSED,
    Outcome.NEEDS_HUMAN: EscalationReason.TOO_MANY_CORRECTIONS,
    Outcome.SPEND_CAP: EscalationReason.SPEND_CAP,
}


def escalate_if_needed(
    log: EventLog, negotiation_id: str, turn: TurnResult, *, at: datetime
) -> EscalationReason | None:
    """Hand the negotiation to a person if the turn produced no action. Returns the reason."""
    reason = REASONS.get(turn.outcome)
    if reason is not None:
        log.append(negotiation_id, Move.ESCALATE, by=Actor.SYSTEM, at=at, reason=reason)
    return reason


def count_escalations(log: EventLog, negotiation_ids: Iterable[str]) -> Counter[EscalationReason]:
    counts: Counter[EscalationReason] = Counter()
    for negotiation_id in negotiation_ids:
        reason = log.saved(negotiation_id).escalated_because
        if reason is not None:
            counts[reason] += 1
    return counts
