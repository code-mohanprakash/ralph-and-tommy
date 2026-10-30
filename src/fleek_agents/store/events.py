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

    def _last(self, negotiation_id: str) -> EventRow | None:
        query = (
            select(EventRow)
            .where(EventRow.negotiation_id == negotiation_id)
            .order_by(EventRow.seq.desc())
            .limit(1)
        )
        return self._session.scalars(query).first()

    def state(self, negotiation_id: str) -> NegotiationState:
        """Where the negotiation is now. With no events yet, it's matched."""
        last = self._last(negotiation_id)
        return NegotiationState(last.to_state) if last else NegotiationState.MATCHED

    def append(
        self,
        negotiation_id: str,
        move: Move,
        *,
        by: Actor,
        at: datetime,
        card: OfferCard | None = None,
    ) -> Event:
        """Save one move, if the rules allow it from the current state. One transaction."""
        last = self._last(negotiation_id)
        from_state = NegotiationState(last.to_state) if last else NegotiationState.MATCHED
        event = Event(
            negotiation_id=negotiation_id,
            seq=last.seq + 1 if last else 1,
            at=at,
            by=by,
            move=move,
            from_state=from_state,
            to_state=next_state(from_state, move, by=by),  # raises IllegalMove
            card=card,
        )
        self._session.add(
            EventRow(
                negotiation_id=event.negotiation_id,
                seq=event.seq,
                move=event.move,
                to_state=event.to_state,
                data=event.model_dump_json(),
            )
        )
        self._session.commit()
        return event

    def read(self, negotiation_id: str) -> list[Event]:
        """Every event in one negotiation, oldest first."""
        query = (
            select(EventRow.data)
            .where(EventRow.negotiation_id == negotiation_id)
            .order_by(EventRow.seq)
        )
        return [Event.model_validate_json(data) for data in self._session.scalars(query)]
