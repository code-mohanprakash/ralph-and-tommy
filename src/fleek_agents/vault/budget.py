"""A buyer's budget across all their deals at once.

Offers are binding, so a buyer negotiating with three sellers could have three offers accepted.
Committed money is every offer of theirs on the table (binding until answered or expired) plus
every deal agreed. A buyer's offer or accept is only made if committed money elsewhere plus this
deal stays within budget, so no combination of sellers accepting can take them past it.
"""

from collections.abc import Callable, Mapping

from fleek_agents.domain.fees import order_total
from fleek_agents.domain.models import Lot
from fleek_agents.domain.money import Pence
from fleek_agents.domain.state import NegotiationState
from fleek_agents.store.events import EventLog
from fleek_agents.store.pairings import lot_of, negotiations_of
from fleek_agents.vault.mandate import BuyerMandate

AGREED = {NegotiationState.PENDING_APPROVAL, NegotiationState.CLOSED}


def committed(
    log: EventLog, buyer_id: str, lots: Mapping[str, Lot], *, leave_out: str = ""
) -> Pence:
    total = Pence(0)
    for negotiation_id in negotiations_of(log.session, buyer_id):
        if negotiation_id == leave_out:
            continue
        snap = log.saved(negotiation_id)
        card = snap.last_offer if snap.state is NegotiationState.OFFERED else None
        if snap.state in AGREED:
            card = snap.agreed
        lot_id = lot_of(log.session, negotiation_id)
        if card is not None and lot_id is not None:
            total = total + order_total(card, lots[lot_id])
    return total


def budget_check(
    log: EventLog, buyer: BuyerMandate, negotiation_id: str, lots: Mapping[str, Lot]
) -> Callable[[Pence], bool]:
    """Would committing `amount` in this negotiation keep the buyer within budget? Yes or no."""

    def within(amount: Pence) -> bool:
        if buyer.budget is None:
            return True
        elsewhere = committed(log, buyer.buyer_id, lots, leave_out=negotiation_id)
        return elsewhere + amount <= buyer.budget.reveal()

    return within
