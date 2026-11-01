"""Offers a seller sent to buyers who walked away: one per buyer per lot, ever."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from fleek_agents.store.db import Base


class SellerOfferRow(Base):
    __tablename__ = "seller_offers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lot_id: Mapped[str] = mapped_column(String(32), index=True)
    buyer_id: Mapped[str] = mapped_column(String(32))
    price: Mapped[int] = mapped_column(Integer)  # base price per piece, pence
    negotiation_id: Mapped[str] = mapped_column(String(32))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def offered(session: Session, lot_id: str) -> set[str]:
    query = select(SellerOfferRow.buyer_id).where(SellerOfferRow.lot_id == lot_id)
    return set(session.scalars(query))


def promised(session: Session, negotiation_id: str) -> int | None:
    query = select(SellerOfferRow.price).where(SellerOfferRow.negotiation_id == negotiation_id)
    return session.scalars(query).first()
