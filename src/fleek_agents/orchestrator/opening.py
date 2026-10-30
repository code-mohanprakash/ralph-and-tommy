"""Opening a negotiation, with the rules that stop a buyer probing the same lot again and again.

One live negotiation per buyer and lot. After one ends without a deal (walked away, expired or
rejected by a person), the same buyer waits `cooldown_hours` before retrying that lot. Losing the
lot to another buyer, or buying it, doesn't count.
"""

from datetime import timedelta

from fleek_agents.config import NegotiationRules
from fleek_agents.domain.state import FINAL_STATES, Actor, Move, NegotiationState
from fleek_agents.orchestrator.clock import Clock
from fleek_agents.store.events import EventLog
from fleek_agents.store.pairings import negotiations_between, new_pairing

FAILED_ENDINGS = {
    NegotiationState.WALKED_AWAY,
    NegotiationState.EXPIRED,
    NegotiationState.REJECTED_BY_HUMAN,
}


class AlreadyNegotiating(Exception):
    """This buyer already has a live negotiation for this lot."""


class CoolingDown(Exception):
    """This buyer's last negotiation for this lot failed less than the cooldown ago."""


def open_negotiation(
    log: EventLog, *, buyer_id: str, lot_id: str, clock: Clock, rules: NegotiationRules
) -> str:
    """Record the pairing and start the negotiation, together. Returns its id."""
    now, cooldown = clock.now(), timedelta(hours=rules.cooldown_hours)
    for earlier in negotiations_between(log.session, buyer_id, lot_id):
        snap = log.saved(earlier)
        if snap.state not in FINAL_STATES:
            raise AlreadyNegotiating(f"{buyer_id} is already negotiating for {lot_id}")
        ended_at = snap.updated_at
        if snap.state in FAILED_ENDINGS and ended_at is not None and now < ended_at + cooldown:
            raise CoolingDown(
                f"{buyer_id} can retry {lot_id} from {ended_at + cooldown:%d %b %H:%M}"
            )

    negotiation_id = new_pairing(log.session, buyer_id=buyer_id, lot_id=lot_id)
    log.stage(negotiation_id, Move.START, by=Actor.SYSTEM, at=now)
    log.session.commit()  # the pairing and the start, or neither
    return negotiation_id
