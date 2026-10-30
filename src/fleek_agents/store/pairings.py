"""Which buyer and which lot each negotiation is about."""

from sqlalchemy import Index, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from fleek_agents.store.db import Base


class PairingRow(Base):
    __tablename__ = "pairings"
    __table_args__ = (Index("pairings_by_buyer_lot", "buyer_id", "lot_id"),)

    # The database numbers rows one at a time, even with many writers, so ids never clash.
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negotiation_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    buyer_id: Mapped[str] = mapped_column(String(32))
    lot_id: Mapped[str] = mapped_column(String(32))


def new_pairing(session: Session, *, buyer_id: str, lot_id: str) -> str:
    """Add a pairing and return its negotiation id, e.g. neg-0007. Doesn't commit."""
    row = PairingRow(buyer_id=buyer_id, lot_id=lot_id)
    session.add(row)
    session.flush()  # the database assigns row.id here
    row.negotiation_id = f"neg-{row.id:04d}"
    return row.negotiation_id


def negotiations_between(session: Session, buyer_id: str, lot_id: str) -> list[str]:
    query = select(PairingRow.negotiation_id).where(
        PairingRow.buyer_id == buyer_id, PairingRow.lot_id == lot_id
    )
    return [n for n in session.scalars(query) if n is not None]


def lot_of(session: Session, negotiation_id: str) -> str | None:
    query = select(PairingRow.lot_id).where(PairingRow.negotiation_id == negotiation_id)
    return session.scalars(query).first()
