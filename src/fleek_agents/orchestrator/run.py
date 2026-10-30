"""Run one negotiation between two agents, turn by turn, under every rule.

The harness asks whose turn it is, builds that side's view, takes one action, and applies it
through the same code everything else uses: send_card (rounds, expiry, one-way concessions), the
vault's can_accept (both limits), and the atomic accept (stock). An accept outside either limit
is refused and handed to a person: the agent doesn't get to break a limit by trying.
"""

from datetime import timedelta

from fleek_agents.agents.base import Accept, Agent, Send, View, WalkAway
from fleek_agents.config import Settings
from fleek_agents.domain.bands import Band
from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.models import Lot, Seller, Want
from fleek_agents.domain.money import Pence
from fleek_agents.domain.rules import quote
from fleek_agents.domain.state import FINAL_STATES, Actor, Move, NegotiationState
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.rounds import send_card
from fleek_agents.store.deals import accept
from fleek_agents.store.events import EventLog
from fleek_agents.vault.bands import buyer_band, seller_band
from fleek_agents.vault.checks import can_accept
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate

THINKING = timedelta(hours=1)  # simulated time between turns


def run_negotiation(
    log: EventLog,
    negotiation_id: str,
    *,
    lot: Lot,
    seller: Seller,
    want: Want,
    bundles: int,
    buyer_limit: BuyerMandate,
    seller_limit: SellerMandate,
    ralph: Agent,
    tommy: Agent,
    clock: FakeClock,
    settings: Settings,
) -> NegotiationState:
    q = quote(lot, seller, bundles=bundles)
    pieces, rules, t = q.pieces, settings.negotiation, settings.bands

    def buyer_band_of(price: Pence) -> Band:
        return buyer_band(buyer_limit, base_price=price, shipping=lot.shipping, pieces=pieces, t=t)

    def seller_band_of(price: Pence) -> Band:
        return seller_band(seller_limit, base_price=price, pieces=pieces, t=t)

    for _ in range(rules.max_rounds + 2):
        snap = log.saved(negotiation_id)
        if snap.state in FINAL_STATES or snap.state is NegotiationState.PENDING_APPROVAL:
            return snap.state
        buyers_turn = snap.state in (NegotiationState.OPEN, NegotiationState.COUNTERED)
        actor = Actor.BUYER_AGENT if buyers_turn else Actor.SELLER_AGENT
        history = tuple(e.card for e in log.read(negotiation_id) if e.card is not None)
        view = View(
            lot=lot,
            want=want if buyers_turn else None,
            bundles=bundles,
            list_price=q.base_price,
            history=history,
            rounds_left=rules.max_rounds - snap.cards,
            band=buyer_band_of if buyers_turn else seller_band_of,
        )
        action = (ralph if buyers_turn else tommy).decide(view)

        if isinstance(action, Send):
            send_card(log, negotiation_id, by=actor, terms=action.terms, clock=clock, rules=rules)
        elif isinstance(action, Accept):
            card = view.on_table
            ok = card is not None and can_accept(
                buyer_limit,
                seller_limit,
                base_price=card.base_price,
                shipping=lot.shipping,
                pieces=card.bundles * lot.pieces,
            )
            if not ok:
                log.append(
                    negotiation_id,
                    Move.ESCALATE,
                    by=Actor.SYSTEM,
                    at=clock.now(),
                    reason=EscalationReason.ACCEPT_OUTSIDE_LIMIT,
                )
            else:
                accept(log, negotiation_id, lot_id=lot.id, by=actor, at=clock.now())
        elif isinstance(action, WalkAway):
            log.append(negotiation_id, Move.WALK_AWAY, by=actor, at=clock.now())
        clock.advance(THINKING)
    return log.saved(negotiation_id).state
