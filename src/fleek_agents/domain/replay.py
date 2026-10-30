"""Rebuild a negotiation's current state by replaying its events, one at a time.

If the log is complete, replaying it gives exactly the state that was saved. A missing event,
an event out of order, or one that doesn't follow from the one before is refused.
"""

from collections.abc import Iterable
from typing import Annotated

from pydantic import AwareDatetime, Field, StrictInt

from fleek_agents.domain.events import EscalationReason, Event
from fleek_agents.domain.models import DomainModel
from fleek_agents.domain.offers import NegotiationId, OfferCard
from fleek_agents.domain.state import Move, NegotiationState


class Snapshot(DomainModel):
    """Where one negotiation stands after its events so far."""

    negotiation_id: NegotiationId
    state: NegotiationState = NegotiationState.MATCHED
    seq: Annotated[StrictInt, Field(ge=0)] = 0  # the last event applied; 0 = none yet
    cards: Annotated[StrictInt, Field(ge=0)] = 0  # offers and counters sent so far
    last_offer: OfferCard | None = None  # the buyer's latest card
    last_counter: OfferCard | None = None  # the seller's latest card
    agreed: OfferCard | None = None  # the card that was accepted, once one is
    escalated_because: EscalationReason | None = None
    updated_at: AwareDatetime | None = None


def apply(snapshot: Snapshot, event: Event) -> Snapshot:
    """The snapshot after one more event."""
    if event.negotiation_id != snapshot.negotiation_id:
        raise ValueError(f"Event {event.seq} belongs to {event.negotiation_id}")
    if event.seq != snapshot.seq + 1:
        raise ValueError(f"Expected event {snapshot.seq + 1}, got {event.seq}")
    if event.from_state is not snapshot.state:
        raise ValueError(f"Event {event.seq} starts from {event.from_state}, not {snapshot.state}")
    changes: dict[str, object] = {
        "state": event.to_state,
        "seq": event.seq,
        "updated_at": event.at,
    }
    if event.move is Move.OFFER:
        changes["last_offer"] = event.card
    elif event.move is Move.COUNTER:
        changes["last_counter"] = event.card
    if event.card is not None:
        changes["cards"] = snapshot.cards + 1
    if event.reason is not None:
        changes["escalated_because"] = event.reason
    if event.move is Move.ACCEPT:  # the other side's card that was on the table
        on_table = {
            NegotiationState.OFFERED: snapshot.last_offer,
            NegotiationState.COUNTERED: snapshot.last_counter,
        }
        changes["agreed"] = on_table.get(snapshot.state)
    return snapshot.model_copy(update=changes)


def replay(negotiation_id: str, events: Iterable[Event]) -> Snapshot:
    """Apply every event in order, starting from 'matched'."""
    snapshot = Snapshot(negotiation_id=negotiation_id)
    for event in events:
        snapshot = apply(snapshot, event)
    return snapshot
