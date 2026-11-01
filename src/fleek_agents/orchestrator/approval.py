"""Approval: who has to say yes before an agreed deal closes.

Every agreed deal passes through pending_approval, so the record always says who approved it: a
person, or the rule (the system). Three kinds of person can be asked:

- the buyer, if they chose to approve every deal themselves (FinalSay.PERSON);
- the seller, likewise;
- a Fleek account manager, for decisions that matter: big deals, a buyer's first few (buyers
  trust automatic deals once they've approved a few; docs/ASSUMPTIONS.md, number 8), a buyer
  the monitors flagged, and a price unusually far below list.

None of this reads a secret limit, and it's all decided after the agents agree, for every deal
of its kind. So waiting for a person can't tell the other side anything about a floor or a top
price: a wait that started only near the floor would (tests/test_approval.py).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from fleek_agents.config import ApprovalRules
from fleek_agents.domain.fees import order_total
from fleek_agents.domain.models import Buyer, FinalSay, Lot, Seller
from fleek_agents.domain.money import Pence
from fleek_agents.domain.state import Actor, IllegalMove, Move, NegotiationState
from fleek_agents.store.approvals import ApprovalRow, asks_for
from fleek_agents.store.deals import give_back_agreed
from fleek_agents.store.events import EventLog
from fleek_agents.store.pairings import PairingRow, lot_of, negotiations_of


class Approver(StrEnum):
    BUYER = "buyer"
    SELLER = "seller"
    ACCOUNT_MANAGER = "account_manager"


class NotAsked(Exception):
    """This person wasn't asked to approve this deal."""


@dataclass(frozen=True)
class Ask:
    who: Approver
    why: str


@dataclass(frozen=True)
class Waiting:
    negotiation_id: str
    buyer_id: str
    lot: Lot
    total: Pence  # what the buyer would pay, fees included
    why: str
    asks: tuple[Ask, ...] = ()  # who still has to say yes


def account_manager_reasons(
    total: Pence,
    *,
    closed_before: int,
    rules: ApprovalRules,
    price: Pence | None = None,
    list_price: Pence | None = None,
    flagged: bool = False,
) -> list[str]:
    reasons = []
    if total.value >= rules.person_at_or_above_pence:
        reasons.append(f"£{rules.person_at_or_above_pence // 100:,} or more")
    if closed_before < rules.first_deals_by_person:
        reasons.append(f"one of the buyer's first {rules.first_deals_by_person} deals")
    if flagged:
        reasons.append("the monitors flagged this buyer")
    if (
        price is not None
        and list_price is not None
        and price.value * 100 < list_price.value * rules.unusual_below_pct
    ):
        reasons.append(f"a price under {rules.unusual_below_pct}% of list")
    return reasons


def needs_person(total: Pence, *, closed_before: int, rules: ApprovalRules) -> bool:
    return bool(account_manager_reasons(total, closed_before=closed_before, rules=rules))


def who_must_approve(
    total: Pence,
    *,
    closed_before: int,
    rules: ApprovalRules,
    price: Pence | None = None,
    list_price: Pence | None = None,
    buyer_says: FinalSay = FinalSay.AGENT,
    seller_says: FinalSay = FinalSay.AGENT,
    flagged: bool = False,
) -> tuple[Ask, ...]:
    """Everyone who has to say yes. Empty: the rule approves it."""
    asks = []
    if buyer_says is FinalSay.PERSON:
        asks.append(Ask(Approver.BUYER, "the buyer approves every deal themselves"))
    if seller_says is FinalSay.PERSON:
        asks.append(Ask(Approver.SELLER, "the seller approves every deal themselves"))
    reasons = account_manager_reasons(
        total,
        closed_before=closed_before,
        rules=rules,
        price=price,
        list_price=list_price,
        flagged=flagged,
    )
    if reasons:
        asks.append(Ask(Approver.ACCOUNT_MANAGER, "; ".join(reasons)))
    return tuple(asks)


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
    buyer: Buyer | None = None,
    seller: Seller | None = None,
    flagged: bool = False,
) -> NegotiationState:
    """Approve an agreed deal by the rule if no person is needed; otherwise ask them."""
    if log.state(negotiation_id) is not NegotiationState.PENDING_APPROVAL:
        return log.state(negotiation_id)
    buyer_id, lot, total = _deal(log, negotiation_id, lots)
    agreed = log.saved(negotiation_id).agreed
    asks = who_must_approve(
        total,
        closed_before=_closed(log, buyer_id),
        rules=rules,
        price=agreed.base_price if agreed is not None else None,
        list_price=lot.base_price,
        buyer_says=buyer.final_say if buyer is not None else FinalSay.AGENT,
        seller_says=seller.final_say if seller is not None else FinalSay.AGENT,
        flagged=flagged,
    )
    if not asks:
        log.append(negotiation_id, Move.APPROVE, by=Actor.SYSTEM, at=at)
    elif not asks_for(log.session, negotiation_id):
        for ask in asks:
            log.session.add(
                ApprovalRow(negotiation_id=negotiation_id, approver=ask.who, why=ask.why)
            )
        log.session.commit()
    return log.state(negotiation_id)


def _still_asked(log: EventLog, negotiation_id: str) -> list[ApprovalRow]:
    return [r for r in asks_for(log.session, negotiation_id) if r.approved_at is None]


def pending(log: EventLog, lots: Mapping[str, Lot], rules: ApprovalRules) -> list[Waiting]:
    """Every deal waiting for a person, with why and who."""
    waiting = []
    for row in log.session.query(PairingRow).order_by(PairingRow.id):
        nid = row.negotiation_id
        if nid and log.state(nid) is NegotiationState.PENDING_APPROVAL:
            buyer_id, lot, total = _deal(log, nid, lots)
            asks = tuple(Ask(Approver(r.approver), r.why) for r in _still_asked(log, nid))
            why = (
                "; ".join(a.why for a in asks)
                if asks
                # Agreed but not settled yet: the account manager's reasons, by amount.
                else "; ".join(account_manager_reasons(total, closed_before=0, rules=rules))
            )
            waiting.append(Waiting(nid, buyer_id, lot, total, why, asks))
    return waiting


def approve(
    log: EventLog,
    negotiation_id: str,
    *,
    at: datetime,
    by: Approver = Approver.ACCOUNT_MANAGER,
) -> None:
    """One person's yes. The deal closes when everyone asked has said yes."""
    if log.state(negotiation_id) is not NegotiationState.PENDING_APPROVAL:
        raise IllegalMove(f"{negotiation_id} isn't waiting for approval")
    asked = asks_for(log.session, negotiation_id)
    if asked:
        mine = [r for r in asked if r.approver == by and r.approved_at is None]
        if not mine:
            raise NotAsked(f"The {by} isn't asked to approve {negotiation_id}")
        mine[0].approved_at = at
        log.session.commit()
        if _still_asked(log, negotiation_id):
            return
    log.append(negotiation_id, Move.APPROVE, by=Actor.HUMAN, at=at)


def reject(
    log: EventLog,
    negotiation_id: str,
    *,
    at: datetime,
    by: Approver = Approver.ACCOUNT_MANAGER,
) -> None:
    """Any one person asked can say no. The stock goes back on sale, in one transaction."""
    asked = asks_for(log.session, negotiation_id)
    if asked and all(r.approver != by for r in asked):
        raise NotAsked(f"The {by} isn't asked to approve {negotiation_id}")
    try:
        log.stage(negotiation_id, Move.REJECT, by=Actor.HUMAN, at=at)
        give_back_agreed(log, negotiation_id)
        log.session.commit()
    except BaseException:
        log.session.rollback()
        raise
