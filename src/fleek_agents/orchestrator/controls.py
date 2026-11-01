"""What a buyer or seller can do to their own negotiation while it runs: stop it, or hand it over.

Neither changes a limit. A limit is fixed once a negotiation on the lot starts
(vault/limits.py): a sudden change in how an agent moves would tell the other side the limit
moved. To change one, stop and start again. Pausing is not a move here: a paused negotiation is
one nobody steps, and its cards still expire after 48 hours (orchestrator/rounds.py).
"""

from datetime import datetime

from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.state import Actor, Move
from fleek_agents.store.events import EventLog


def stop(log: EventLog, negotiation_id: str, *, at: datetime) -> None:
    """End it with no deal. IllegalMove once it's agreed or over: then it's approve or reject."""
    log.append(negotiation_id, Move.STOP, by=Actor.HUMAN, at=at)


def hand_over(log: EventLog, negotiation_id: str, *, at: datetime) -> None:
    """Hand it to an account manager, who finishes it by hand (humans/handover.py)."""
    log.append(
        negotiation_id,
        Move.ESCALATE,
        by=Actor.SYSTEM,
        at=at,
        reason=EscalationReason.ASKED_FOR_A_PERSON,
    )
