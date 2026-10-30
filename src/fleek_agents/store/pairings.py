"""Which buyer and which lot each negotiation is about."""

from sqlalchemy import Index, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from fleek_agents.store.db import Base


class PairingRow(Base):
    __tablename__ = "pairings"
    __table_args__ = (Index("pairings_by_buyer_lot", "buyer_id", "lot_id"),)

    negotiation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    buyer_id: Mapped[str] = mapped_column(String(32))
    lot_id: Mapped[str] = mapped_column(String(32))


def negotiations_between(session: Session, buyer_id: str, lot_id: str) -> list[str]:
    query = select(PairingRow.negotiation_id).where(
        PairingRow.buyer_id == buyer_id, PairingRow.lot_id == lot_id
    )
    return list(session.scalars(query))


def next_negotiation_id(session: Session) -> str:
    count = session.scalar(select(func.count()).select_from(PairingRow)) or 0
    return f"neg-{count + 1:04d}"
