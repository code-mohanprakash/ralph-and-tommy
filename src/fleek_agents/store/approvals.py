"""Who has to approve each agreed deal, and who has. One row per person asked."""

from datetime import datetime

from sqlalchemy import DateTime, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from fleek_agents.store.db import Base


class ApprovalRow(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negotiation_id: Mapped[str] = mapped_column(String(32), index=True)
    approver: Mapped[str] = mapped_column(String(32))  # buyer, seller or account_manager
    why: Mapped[str] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


def asks_for(session: Session, negotiation_id: str) -> list[ApprovalRow]:
    query = select(ApprovalRow).where(ApprovalRow.negotiation_id == negotiation_id)
    return list(session.scalars(query.order_by(ApprovalRow.id)))
