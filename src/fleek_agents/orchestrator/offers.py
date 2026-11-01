"""The seller's offer to buyers who walked away (eBay's "offers to buyers", Depop's "send offer").

A seller can set, before the lot goes on sale, a public % off that goes once to each buyer who
walked away from it. Code keeps the promise: when the buyer's agent offers that price, the lot's
agent doesn't get a say, the referee accepts it (inside the vault's checks, like any accept).
The price was checked against the floor when the seller set it (vault/offers.py), and every
buyer who walks away gets the same one, so receiving it says nothing about the floor.
"""

from fleek_agents.config import NegotiationRules
from fleek_agents.domain.models import Lot
from fleek_agents.domain.rules import walkaway_offer_price
from fleek_agents.domain.state import Actor, Move, NegotiationState
from fleek_agents.orchestrator.clock import Clock
from fleek_agents.orchestrator.opening import NoTriesLeft, open_negotiation
from fleek_agents.store.events import EventLog
from fleek_agents.store.offers import SellerOfferRow, offered
from fleek_agents.store.pairings import PairingRow, negotiations_for_lot


def walked_away(log: EventLog, lot_id: str) -> list[str]:
    """Buyers whose agent walked away from this lot (or let it expire), not yet sent an offer."""
    already = offered(log.session, lot_id)
    buyers: list[str] = []
    for nid in negotiations_for_lot(log.session, lot_id):
        snap = log.saved(nid)
        ended_by_buyer = snap.state is NegotiationState.EXPIRED or any(
            e.move is Move.WALK_AWAY and e.by is Actor.BUYER_AGENT for e in log.read(nid)
        )
        buyer = log.session.query(PairingRow).filter_by(negotiation_id=nid).one().buyer_id
        if ended_by_buyer and buyer not in already and buyer not in buyers:
            buyers.append(buyer)
    return buyers


def send_walkaway_offers(
    log: EventLog, lot: Lot, *, clock: Clock, rules: NegotiationRules
) -> dict[str, str]:
    """Open one invited negotiation per buyer who walked away. Returns buyer id: negotiation id."""
    price = walkaway_offer_price(lot)
    if price is None:
        return {}
    sent = {}
    for buyer_id in walked_away(log, lot.id):
        try:
            nid = open_negotiation(
                log, buyer_id=buyer_id, lot_id=lot.id, clock=clock, rules=rules, invited=True
            )
        except NoTriesLeft:
            continue  # the cap on tries holds even for offers
        log.session.add(
            SellerOfferRow(
                lot_id=lot.id,
                buyer_id=buyer_id,
                price=price.value,
                negotiation_id=nid,
                sent_at=clock.now(),
            )
        )
        log.session.commit()
        sent[buyer_id] = nid
    return sent
