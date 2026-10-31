"""The account manager's summary: whenever a person is needed, what happened and what to do.

A person is needed in three cases:
- a deal is agreed but waits for approval (big, or one of a buyer's first deals);
- the referee stopped a move and handed the negotiation over (an agent tried to break a limit,
  the AI refused or kept getting it wrong, the spend cap, the buyer's budget);
- no deal, but it ended close enough to be worth a call (the near-miss list).

Built from the event log by plain code, no AI, so it can't make anything up. It holds no secret
limit: only the prices on the cards, the reason a person was asked, and Fleek's fees. An import
rule (pyproject.toml) stops this package from reaching the vault at all.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from fleek_agents.config import ApprovalRules, DigestRules
from fleek_agents.domain.events import EscalationReason, Event
from fleek_agents.domain.fees import order_total
from fleek_agents.domain.models import Lot
from fleek_agents.domain.money import Pence
from fleek_agents.domain.state import Actor, Move, NegotiationState
from fleek_agents.humans.digest import call_list
from fleek_agents.orchestrator.approval import pending
from fleek_agents.store.events import EventLog
from fleek_agents.store.pairings import PairingRow

NAME = {Actor.BUYER_AGENT: "Ralph (buyer's agent)", Actor.SELLER_AGENT: "Tommy (seller's agent)"}
SHORT = {Actor.BUYER_AGENT: "Ralph", Actor.SELLER_AGENT: "Tommy"}

# Who should get the call, and what to check, for each reason the referee hands over.
STOPPED = {
    EscalationReason.CARD_OUTSIDE_LIMIT: (
        "{agent} tried to send a card past its own side's limit. The referee stopped it, so the "
        "other side never saw it.",
        "Call the {side}: check the limit they set is still what they mean. Then restart the "
        "negotiation or close it.",
    ),
    EscalationReason.ACCEPT_OUTSIDE_LIMIT: (
        "{agent} tried to accept a price outside a limit. The referee refused.",
        "Call the {side}: check the limit they set. Then restart the negotiation or close it.",
    ),
    EscalationReason.OVER_BUDGET: (
        "This move would have taken the buyer past their budget across all their open deals.",
        "Call the buyer: ask which deals matter most, or whether the budget should change.",
    ),
    EscalationReason.MODEL_REFUSED: (
        "{agent}'s AI refused to answer.",
        "Read the last cards and finish the negotiation by hand, or close it.",
    ),
    EscalationReason.TOO_MANY_CORRECTIONS: (
        "{agent}'s AI kept giving answers the rules don't allow.",
        "Read the last cards and finish the negotiation by hand, or close it.",
    ),
    EscalationReason.SPEND_CAP: (
        "The AI spending limit for this negotiation was reached.",
        "Finish it by hand, or close it. If this happens often, look at the cap in market.toml.",
    ),
}


@dataclass(frozen=True)
class Handover:
    negotiation_id: str
    kind: str  # approve, stopped or near_miss
    why: str  # why you're seeing this, in one or two sentences
    happened: tuple[str, ...]  # every move, in order, in plain words
    stands: str  # where it stands now
    todo: str  # what to do
    buyer_id: str
    lot_title: str
    at_stake: Pence  # what the buyer pays, or would pay at the last counter


def _moves(events: list[Event]) -> tuple[str, ...]:
    lines = []
    for e in events:
        who = SHORT.get(e.by, "Fleek")
        if e.move in (Move.OFFER, Move.COUNTER) and e.card is not None:
            verb = "offered" if e.move is Move.OFFER else "countered at"
            lines.append(f"{who} {verb} {e.card.base_price} a piece for {e.card.bundles} bundle(s)")
        elif e.move is Move.ACCEPT:
            lines.append(f"{who} accepted")
        elif e.move is Move.WALK_AWAY:
            lines.append(f"{who} walked away")
        elif e.move is Move.ESCALATE:
            lines.append(f"The referee stopped the negotiation ({e.reason})")
        elif e.move is Move.EXPIRE:
            lines.append("48 hours passed with no answer")
    return tuple(lines)


def _stopped_by(events: list[Event]) -> Actor:
    """Whose turn it was when the referee stopped it: the buyer moves after a counter."""
    stop = next(e for e in reversed(events) if e.move is Move.ESCALATE)
    if stop.from_state is NegotiationState.OFFERED:
        return Actor.SELLER_AGENT
    return Actor.BUYER_AGENT


def handover(
    log: EventLog,
    negotiation_id: str,
    lots: Mapping[str, Lot],
    *,
    approval: ApprovalRules,
    digest: DigestRules,
) -> Handover | None:
    """The summary for one negotiation, or None when no person is needed."""
    row = log.session.query(PairingRow).filter_by(negotiation_id=negotiation_id).one()
    lot = lots[row.lot_id]
    snap = log.saved(negotiation_id)
    events = log.read(negotiation_id)
    happened = _moves(events)

    def make(kind: str, why: str, stands: str, todo: str, at_stake: Pence) -> Handover:
        return Handover(
            negotiation_id, kind, why, happened, stands, todo, row.buyer_id, lot.title, at_stake
        )

    if snap.state is NegotiationState.PENDING_APPROVAL and snap.agreed is not None:
        waiting = next(
            w for w in pending(log, lots, approval) if w.negotiation_id == negotiation_id
        )
        pieces = snap.agreed.bundles * lot.pieces
        return make(
            "approve",
            f"An agreed deal waits for your OK: {waiting.why}.",
            f"Agreed at {snap.agreed.base_price} a piece for {pieces} pieces. The buyer pays "
            f"{waiting.total}. The referee checked it is inside both private limits, and the "
            "stock is held.",
            "Check the buyer and the lot look right, then approve. If you reject, the stock "
            "goes back on sale.",
            waiting.total,
        )

    if snap.state is NegotiationState.NEEDS_HUMAN and snap.escalated_because is not None:
        agent = _stopped_by(events)
        side = "seller" if agent is Actor.SELLER_AGENT else "buyer"
        why, todo = STOPPED[snap.escalated_because]
        other = Actor.SELLER_AGENT if agent is Actor.BUYER_AGENT else Actor.BUYER_AGENT
        last = snap.last_counter if other is Actor.SELLER_AGENT else snap.last_offer
        on_table = (
            f"On the table: {SHORT[other]}'s {last.base_price} a piece."
            if last is not None
            else "No card on the table yet."
        )
        return make(
            "stopped",
            why.format(agent=NAME[agent], side=side),
            f"Paused, no deal yet. {on_table}",
            todo.format(agent=NAME[agent], side=side),
            order_total(last, lot) if last is not None else Pence(0),
        )

    near = next(
        (i for i in call_list(log, lots, digest) if i.negotiation_id == negotiation_id), None
    )
    if near is not None:
        gap = near.last_counter - near.last_offer
        return make(
            "near_miss",
            f"No deal, but it ended close: the last offer and counter were {near.gap_pct}% apart.",
            f"Ralph's last offer {near.last_offer}, Tommy's last counter {near.last_counter}: "
            f"{gap} a piece apart. At the counter the buyer would have paid {near.value}.",
            "Call the seller first: a small move may close it. Then the buyer.",
            near.value,
        )
    return None
