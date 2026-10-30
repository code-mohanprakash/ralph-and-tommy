"""Sending cards and expiring them, under Fleek's Make an Offer rules.

An agent decides the terms. The harness fills in everything else: which negotiation, which round,
from which side, and when it expires. So an agent can't send a card that lasts forever or skip
ahead a round.
"""

from collections.abc import Iterable
from datetime import timedelta

from fleek_agents.config import NegotiationRules
from fleek_agents.domain.events import Event
from fleek_agents.domain.offers import OfferCard, Role, Terms
from fleek_agents.domain.state import Actor, Move, NegotiationState
from fleek_agents.orchestrator.clock import Clock
from fleek_agents.store.deals import give_back
from fleek_agents.store.events import EventLog
from fleek_agents.store.pairings import lot_of

SIDES = {
    Actor.BUYER_AGENT: (Role.BUYER, Move.OFFER),
    Actor.SELLER_AGENT: (Role.SELLER, Move.COUNTER),
}


class RoundLimitReached(Exception):
    """No more cards: the side can only accept or walk away."""


class BackwardsConcession(Exception):
    """A buyer lowering their offer, or a seller raising their counter."""


def send_card(
    log: EventLog,
    negotiation_id: str,
    *,
    by: Actor,
    terms: Terms,
    clock: Clock,
    rules: NegotiationRules,
) -> Event:
    """An offer (from the buyer's agent) or counter (from the seller's), numbered and timed."""
    if by not in SIDES:
        raise ValueError(f"Only the agents send cards, not {by}")
    role, move = SIDES[by]
    snapshot = log.saved(negotiation_id)
    if snapshot.cards >= rules.max_rounds:
        raise RoundLimitReached(f"{rules.max_rounds} cards sent; accept or walk away")
    # Concessions only go one way, so walking a price up and down can't map out a limit.
    previous = snapshot.last_offer if role is Role.BUYER else snapshot.last_counter
    if previous is not None:
        if role is Role.BUYER and terms.base_price < previous.base_price:
            raise BackwardsConcession("A buyer's offer can only stay the same or go up")
        if role is Role.SELLER and terms.base_price > previous.base_price:
            raise BackwardsConcession("A seller's counter can only stay the same or go down")
    now = clock.now()
    card = OfferCard(
        negotiation_id=negotiation_id,
        round=snapshot.cards + 1,
        from_role=role,
        expires_at=now + timedelta(hours=rules.answer_hours),
        **terms.model_dump(),
    )
    return log.append(negotiation_id, move, by=by, at=now, card=card)


def expire_due(
    log: EventLog, negotiation_ids: Iterable[str], *, clock: Clock, rules: NegotiationRules
) -> list[str]:
    """Expire every negotiation whose 48 hours are up. Returns the ones it expired."""
    now, wait = clock.now(), timedelta(hours=rules.answer_hours)
    expired = []
    for negotiation_id in negotiation_ids:
        snap = log.saved(negotiation_id)
        on_table = {
            NegotiationState.OFFERED: snap.last_offer,
            NegotiationState.COUNTERED: snap.last_counter,
        }.get(snap.state)
        if on_table is not None:
            deadline = on_table.expires_at  # the card says when it expires
        elif snap.state in (NegotiationState.OPEN, NegotiationState.PENDING_APPROVAL):
            if snap.updated_at is None:  # can't happen: both states are reached by an event
                raise ValueError(f"{negotiation_id} is {snap.state} but has no events")
            deadline = snap.updated_at + wait  # waiting on a first offer, or on approval
        else:
            continue  # matched, or already ended
        if now >= deadline:
            log.stage(negotiation_id, Move.EXPIRE, by=Actor.SYSTEM, at=now)
            if snap.state is NegotiationState.PENDING_APPROVAL:
                # The stock was taken at accept. An expired approval puts it back on sale.
                lot_id = lot_of(log.session, negotiation_id)
                if lot_id is None or snap.agreed is None:
                    log.session.rollback()
                    raise ValueError(f"{negotiation_id} is waiting for approval with no lot")
                give_back(log.session, lot_id, bundles=snap.agreed.bundles)
            log.session.commit()  # the expiry and the stock, or neither
            expired.append(negotiation_id)
    return expired
