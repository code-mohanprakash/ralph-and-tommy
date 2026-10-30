"""The market in the database, and the hard filters that run first in matching.

The filters are exact and nearly free, so they run before anything that costs time or money:
right category, right brand (if the buyer named one), an acceptable grade, still in stock, and a
bundle no bigger than twice what the buyer wants.
"""

from sqlalchemy import Index, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from fleek_agents.domain.models import Lot, Market, Want
from fleek_agents.store.db import Base
from fleek_agents.store.deals import StockRow

BIGGEST_BUNDLE = 2  # a bundle may be up to twice the pieces the buyer wants


class LotRow(Base):
    __tablename__ = "lots"
    __table_args__ = (Index("lots_by_category_grade", "category", "grade"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    seller_id: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(64))
    brand: Mapped[str] = mapped_column(String(64))
    grade: Mapped[str] = mapped_column(String(8))
    pieces: Mapped[int]
    data: Mapped[str] = mapped_column(Text)  # the whole Lot as JSON


def load_market(session: Session, market: Market) -> None:
    """Put every lot in the database, with its stock on sale. One transaction."""
    for lot in market.lots:
        session.add(
            LotRow(
                id=lot.id,
                seller_id=lot.seller_id,
                category=lot.category,
                brand=lot.brand,
                grade=lot.grade,
                pieces=lot.pieces,
                data=lot.model_dump_json(),
            )
        )
        session.add(StockRow(lot_id=lot.id, available=lot.available))
    session.commit()


def hard_filter(session: Session, want: Want) -> list[Lot]:
    """Lots that pass every hard rule for this want, in id order."""
    query = (
        select(LotRow.data)
        .join(StockRow, StockRow.lot_id == LotRow.id)
        .where(
            LotRow.category == want.category,
            LotRow.grade.in_([str(g) for g in want.grades]),
            LotRow.pieces <= want.pieces * BIGGEST_BUNDLE,
            StockRow.available >= 1,
        )
        .order_by(LotRow.id)
    )
    if want.brands:
        query = query.where(LotRow.brand.in_(want.brands))
    return [Lot.model_validate_json(data) for data in session.scalars(query)]
