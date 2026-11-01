"""Opening a negotiation, with the rules that stop a buyer probing the same lot again and again.

One live negotiation per buyer and lot. After one ends without a deal (walked away, expired or
rejected by a person), the same buyer waits `cooldown_hours` before retrying that lot, and after
`tries_per_buyer_per_lot` failed tries they can't open it again. Losing the lot to another buyer,
or buying it, doesn't count.
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
    NegotiationState.STOPPED,  # or a prober could stop each try to keep it from counting
}


class AlreadyNegotiating(Exception):
    """This buyer already has a live negotiation for this lot."""


class CoolingDown(Exception):
    """This buyer's last negotiation for this lot failed less than the cooldown ago."""


class NoTriesLeft(Exception):
    """This buyer has used every try they get on this lot."""


def open_negotiation(
    log: EventLog,
    *,
    buyer_id: str,
    lot_id: str,
    clock: Clock,
    rules: NegotiationRules,
    invited: bool = False,
) -> str:
    """Record the pairing and start the negotiation, together. Returns its id.

    invited: the seller sent this buyer an offer, so the cooldown doesn't apply. The cap on
    tries still does.
    """
    now, cooldown = clock.now(), timedelta(hours=rules.cooldown_hours)
    earlier_ones = negotiations_between(log.session, buyer_id, lot_id)
    failed = sum(log.saved(n).state in FAILED_ENDINGS for n in earlier_ones)
    if failed >= rules.tries_per_buyer_per_lot:
        raise NoTriesLeft(
            f"{buyer_id} has used all {rules.tries_per_buyer_per_lot} tries on {lot_id}"
        )
    for earlier in earlier_ones:
        snap = log.saved(earlier)
        if snap.state not in FINAL_STATES:
            raise AlreadyNegotiating(f"{buyer_id} is already negotiating for {lot_id}")
        ended_at = snap.updated_at
        if invited or snap.state not in FAILED_ENDINGS or ended_at is None:
            continue
        if now < ended_at + cooldown:
            raise CoolingDown(
                f"{buyer_id} can retry {lot_id} from {ended_at + cooldown:%d %b %H:%M}"
            )

    negotiation_id = new_pairing(log.session, buyer_id=buyer_id, lot_id=lot_id)
    log.stage(negotiation_id, Move.START, by=Actor.SYSTEM, at=now)
    log.session.commit()  # the pairing and the start, or neither
    return negotiation_id
