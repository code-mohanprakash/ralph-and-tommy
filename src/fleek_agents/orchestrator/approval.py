"""Approval: big deals, and a buyer's first few, wait for a person.

Buyers trust automatic deals once they've approved a few themselves (docs/ASSUMPTIONS.md, number
8), and big amounts deserve a second look. Every agreed deal passes through pending_approval, so
the record always says who approved it: a person, or the rule (the system).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from fleek_agents.config import ApprovalRules
from fleek_agents.domain.models import Lot
from fleek_agents.domain.money import Pence
from fleek_agents.domain.state import Actor, IllegalMove, Move, NegotiationState
from fleek_agents.store.deals import give_back_agreed
from fleek_agents.store.events import EventLog
from fleek_agents.store.pairings import PairingRow, lot_of, negotiations_of
from fleek_agents.vault.budget import order_total


@dataclass(frozen=True)
class Waiting:
    negotiation_id: str
    buyer_id: str
    lot: Lot
    total: Pence  # what the buyer would pay, fees included
    why: str


def needs_person(total: Pence, *, closed_before: int, rules: ApprovalRules) -> bool:
    return (
        total.value >= rules.person_at_or_above_pence or closed_before < rules.first_deals_by_person
    )


def _why(total: Pence, rules: ApprovalRules) -> str:
    if total.value >= rules.person_at_or_above_pence:
        return f"£{rules.person_at_or_above_pence // 100:,} or more"
    return f"one of the buyer's first {rules.first_deals_by_person} deals"


def _closed(log: EventLog, buyer_id: str) -> int:
    return sum(
        log.state(n) is NegotiationState.CLOSED for n in negotiations_of(log.session, buyer_id)
    )


def _deal(log: EventLog, negotiation_id: str, lots: Mapping[str, Lot]) -> tuple[str, Lot, Pence]:
    row = log.session.query(PairingRow).filter_by(negotiation_id=negotiation_id).one()
    snap = log.saved(negotiation_id)
    lot_id = lot_of(log.session, negotiation_id)
    if snap.agreed is None or lot_id is None:
        raise IllegalMove(f"{negotiation_id} has no agreed deal")
    return row.buyer_id, lots[lot_id], order_total(snap.agreed, lots[lot_id])


def settle(
    log: EventLog,
    negotiation_id: str,
    *,
    lots: Mapping[str, Lot],
    rules: ApprovalRules,
    at: datetime,
) -> NegotiationState:
    """Approve an agreed deal by the rule if no person is needed; otherwise leave it waiting."""
    if log.state(negotiation_id) is not NegotiationState.PENDING_APPROVAL:
        return log.state(negotiation_id)
    buyer_id, _, total = _deal(log, negotiation_id, lots)
    if not needs_person(total, closed_before=_closed(log, buyer_id), rules=rules):
        log.append(negotiation_id, Move.APPROVE, by=Actor.SYSTEM, at=at)
    return log.state(negotiation_id)


def pending(log: EventLog, lots: Mapping[str, Lot], rules: ApprovalRules) -> list[Waiting]:
    """Every deal waiting for a person, with why it's waiting."""
    waiting = []
    for row in log.session.query(PairingRow).order_by(PairingRow.id):
        if (
            row.negotiation_id
            and log.state(row.negotiation_id) is NegotiationState.PENDING_APPROVAL
        ):
            buyer_id, lot, total = _deal(log, row.negotiation_id, lots)
            why = _why(total, rules)
            waiting.append(Waiting(row.negotiation_id, buyer_id, lot, total, why))
    return waiting


def approve(log: EventLog, negotiation_id: str, *, at: datetime) -> None:
    log.append(negotiation_id, Move.APPROVE, by=Actor.HUMAN, at=at)  # IllegalMove unless waiting


def reject(log: EventLog, negotiation_id: str, *, at: datetime) -> None:
    """Reject a waiting deal and put its stock back on sale, in one transaction."""
    try:
        log.stage(negotiation_id, Move.REJECT, by=Actor.HUMAN, at=at)
        give_back_agreed(log, negotiation_id)
        log.session.commit()
    except BaseException:
        log.session.rollback()
        raise
