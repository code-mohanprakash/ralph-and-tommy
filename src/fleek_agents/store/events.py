"""The events log: every move in every negotiation, in order, never edited.

It's the audit trail, the source for replaying a deal, and the evidence if a buyer and seller
disagree about what happened.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Connection, String, Text, UniqueConstraint, event, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from fleek_agents.domain.events import Event
from fleek_agents.domain.offers import OfferCard
from fleek_agents.domain.replay import Snapshot, apply
from fleek_agents.domain.state import Actor, Move, NegotiationState, next_state
from fleek_agents.store.db import Base


class EventRow(Base):
    __tablename__ = "events"
    # Two writers can't both save event 3 of the same negotiation.
    __table_args__ = (UniqueConstraint("negotiation_id", "seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    negotiation_id: Mapped[str] = mapped_column(String(32), index=True)
    seq: Mapped[int]
    move: Mapped[str] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32))
    data: Mapped[str] = mapped_column(Text)  # the whole event as JSON, exactly as validated


class NegotiationRow(Base):
    """Each negotiation's current snapshot, saved in the same transaction as its events."""

    __tablename__ = "negotiations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    seq: Mapped[int]
    data: Mapped[str] = mapped_column(Text)  # the Snapshot as JSON


@event.listens_for(EventRow.__table__, "after_create")
def _make_append_only(_table: Any, connection: Connection, **_: Any) -> None:
    """The database itself refuses to change or remove an event, whatever code asks."""
    for action in ("UPDATE", "DELETE"):
        connection.exec_driver_sql(
            f"CREATE TRIGGER events_no_{action.lower()} BEFORE {action} ON events "
            "BEGIN SELECT RAISE(ABORT, 'events are append-only'); END"
        )


class EventLog:
    """Add moves and read them back. There is no way to change or remove one."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def saved(self, negotiation_id: str) -> Snapshot:
        """The saved snapshot. A negotiation with no events yet is 'matched'."""
        row = self._session.get(NegotiationRow, negotiation_id)
        if row is None:
            return Snapshot(negotiation_id=negotiation_id)
        return Snapshot.model_validate_json(row.data)

    def state(self, negotiation_id: str) -> NegotiationState:
        """Where the negotiation is now."""
        return self.saved(negotiation_id).state

    def append(
        self,
        negotiation_id: str,
        move: Move,
        *,
        by: Actor,
        at: datetime,
        card: OfferCard | None = None,
    ) -> Event:
        """Save one move and the new snapshot together, if the rules allow the move."""
        before = self.saved(negotiation_id)
        event = Event(
            negotiation_id=negotiation_id,
            seq=before.seq + 1,
            at=at,
            by=by,
            move=move,
            from_state=before.state,
            to_state=next_state(before.state, move, by=by),  # raises IllegalMove
            card=card,
        )
        after = apply(before, event)
        self._session.add(
            EventRow(
                negotiation_id=event.negotiation_id,
                seq=event.seq,
                move=event.move,
                to_state=event.to_state,
                data=event.model_dump_json(),
            )
        )
        self._session.merge(
            NegotiationRow(
                id=negotiation_id, state=after.state, seq=after.seq, data=after.model_dump_json()
            )
        )
        self._session.commit()  # both rows, or neither
        return event

    def read(self, negotiation_id: str) -> list[Event]:
        """Every event in one negotiation, oldest first."""
        query = (
            select(EventRow.data)
            .where(EventRow.negotiation_id == negotiation_id)
            .order_by(EventRow.seq)
        )
        return [Event.model_validate_json(data) for data in self._session.scalars(query)]
