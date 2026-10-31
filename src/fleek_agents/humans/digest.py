"""The near-miss call list: which failed negotiations are worth an account manager's call.

Built from facts in the record only, no AI: negotiations that ended without a deal, where the
buyer's last offer and the seller's last counter ended up close, biggest first. It shows only what
both sides already saw on the cards; no secret limit is in it.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from fleek_agents.config import DigestRules
from fleek_agents.domain.fees import order_total
from fleek_agents.domain.models import Lot
from fleek_agents.domain.money import Pence
from fleek_agents.domain.state import NegotiationState
from fleek_agents.store.events import EventLog
from fleek_agents.store.pairings import PairingRow

NO_DEAL = {
    NegotiationState.WALKED_AWAY,
    NegotiationState.EXPIRED,
    NegotiationState.NEEDS_HUMAN,
    NegotiationState.REJECTED_BY_HUMAN,
}


@dataclass(frozen=True)
class CallItem:
    negotiation_id: str
    buyer_id: str
    lot_title: str
    ended: str  # how it ended, with the reason if a person was asked
    last_offer: Pence  # base price per piece
    last_counter: Pence
    gap_pct: int  # how far apart, as a % of the counter
    value: Pence  # what the buyer would have paid at the last counter, fees included


def call_list(log: EventLog, lots: Mapping[str, Lot], rules: DigestRules) -> list[CallItem]:
    items = []
    for row in log.session.query(PairingRow).order_by(PairingRow.id):
        if row.negotiation_id is None:
            continue
        snap = log.saved(row.negotiation_id)
        offer, counter = snap.last_offer, snap.last_counter
        if snap.state not in NO_DEAL or offer is None or counter is None:
            continue
        gap_pct = (
            max(0, counter.base_price.value - offer.base_price.value)
            * 100
            // counter.base_price.value
        )
        if gap_pct > rules.near_miss_gap_pct:
            continue
        ended = str(snap.state)
        if snap.escalated_because is not None:
            ended += f": {snap.escalated_because}"
        items.append(
            CallItem(
                negotiation_id=row.negotiation_id,
                buyer_id=row.buyer_id,
                lot_title=lots[row.lot_id].title,
                ended=ended,
                last_offer=offer.base_price,
                last_counter=counter.base_price,
                gap_pct=gap_pct,
                value=order_total(counter, lots[row.lot_id]),
            )
        )
    items.sort(key=lambda i: (-i.value.value, i.gap_pct))
    return items[: rules.list_size]
