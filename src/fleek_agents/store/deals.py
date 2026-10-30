"""Accepting a deal: take the stock and record the accept together, or do neither.

Most lots on Fleek have only one available, so two buyers can accept the same lot at nearly the
same moment. The stock is taken by one conditional UPDATE, which the database runs one at a time:
the first accept takes it, and any later one finds nothing left and is told the lot is sold.
"""

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, String, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from fleek_agents.domain.state import LIVE, Actor, IllegalMove, Move, NegotiationState
from fleek_agents.store.db import Base
from fleek_agents.store.events import EventLog


class StockRow(Base):
    __tablename__ = "stock"
    __table_args__ = (CheckConstraint("available >= 0", name="stock_never_negative"),)

    lot_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    available: Mapped[int]  # bundles left


class AcceptOutcome(StrEnum):
    WON = "won"  # the stock is taken; the deal waits for approval
    SOLD_OUT = "sold_out"  # someone else got there first


def put_on_sale(session: Session, lot_id: str, *, bundles: int) -> None:
    session.add(StockRow(lot_id=lot_id, available=bundles))
    session.commit()


def stock_left(session: Session, lot_id: str) -> int:
    row = session.get(StockRow, lot_id, populate_existing=True)
    return row.available if row else 0


def accept(
    log: EventLog,
    negotiation_id: str,
    *,
    lot_id: str,
    by: Actor,
    at: datetime,
    rivals: Iterable[str] = (),
) -> AcceptOutcome:
    """Accept the other side's card on the table, in one transaction."""
    session = log.session
    try:
        snapshot = log.saved(negotiation_id)
        on_table = {
            NegotiationState.OFFERED: snapshot.last_offer,
            NegotiationState.COUNTERED: snapshot.last_counter,
        }.get(snapshot.state)
        if on_table is None:
            raise IllegalMove(f"Nothing to accept when the negotiation is {snapshot.state}")

        # Take the stock only if enough is left. The database checks and takes in one step.
        taken = session.execute(
            update(StockRow)
            .where(StockRow.lot_id == lot_id, StockRow.available >= on_table.bundles)
            .values(available=StockRow.available - on_table.bundles)
        )
        if taken.rowcount == 0:  # type: ignore[attr-defined]  # rowcount exists on UPDATE results
            session.rollback()
            if log.state(negotiation_id) in LIVE:
                log.append(negotiation_id, Move.LOSE_LOT, by=Actor.SYSTEM, at=at)
            return AcceptOutcome.SOLD_OUT

        log.stage(negotiation_id, Move.ACCEPT, by=by, at=at)  # raises IllegalMove if not allowed
        if stock_left(session, lot_id) == 0:
            for rival in rivals:
                if rival != negotiation_id and log.state(rival) in LIVE:
                    log.stage(rival, Move.LOSE_LOT, by=Actor.SYSTEM, at=at)
        session.commit()
        return AcceptOutcome.WON
    except BaseException:
        session.rollback()  # nothing half-done: no stock taken, no events saved
        raise
