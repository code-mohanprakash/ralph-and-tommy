"""Run one negotiation between two agents, turn by turn, under every rule.

The harness asks whose turn it is, builds that side's view, takes one action, and applies it
through the same code everything else uses: send_card (rounds, expiry, one-way concessions), the
vault's can_accept (both limits), and the atomic accept (stock). An accept outside either limit
is refused and handed to a person: the agent doesn't get to break a limit by trying.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from fleek_agents.agents.base import Accept, Action, Agent, HandOff, Send, View, WalkAway
from fleek_agents.config import Settings
from fleek_agents.domain.bands import Band
from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.fees import buyer_pays
from fleek_agents.domain.models import Lot, Seller, Want
from fleek_agents.domain.money import Pence
from fleek_agents.domain.rules import quote
from fleek_agents.domain.state import FINAL_STATES, Actor, Move, NegotiationState
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.rounds import send_card
from fleek_agents.store.deals import accept
from fleek_agents.store.events import EventLog
from fleek_agents.vault.bands import buyer_band, seller_band
from fleek_agents.vault.checks import buyer_ok, can_accept, seller_ok
from fleek_agents.vault.firm import working_limit
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate
from fleek_agents.vault.privacy import guarded, jitter

THINKING = timedelta(hours=1)  # simulated time between turns


def _order_total(action: Send | Accept, view: View, lot: Lot) -> Pence:
    """What the buyer would be committing: their new offer, or the counter they'd accept."""
    price = action.terms.base_price if isinstance(action, Send) else None
    bundles = action.terms.bundles if isinstance(action, Send) else view.bundles
    if price is None:
        card = view.on_table
        if card is None:
            return Pence(0)
        price, bundles = card.base_price, card.bundles
    return buyer_pays(base_price=price, shipping=lot.shipping, pieces=bundles * lot.pieces).total


@dataclass
class Deal:
    """Everything one negotiation needs, so several can be run side by side."""

    negotiation_id: str
    lot: Lot
    seller: Seller
    want: Want
    bundles: int
    buyer_limit: BuyerMandate
    seller_limit: SellerMandate
    ralph: Agent
    tommy: Agent
    within_budget: Callable[[Pence], bool] = lambda _: True
    elsewhere: Callable[[], tuple[str, ...]] = lambda: ()  # the buyer's other open deals
    # The lot as Ralph sees it. With the listing reader on, its description is the reader's
    # fixed summary, not the seller's words (harness/reader.py). Tommy and every check use `lot`.
    buyer_lot: Lot | None = None
    # The seller's offer to a buyer who walked away (orchestrator/offers.py): the referee
    # accepts any buyer offer at or above it on the seller's behalf.
    promised: Pence | None = None


def _inside_own_limit(
    action: Send, deal: Deal, seller_limit: SellerMandate, buyers_turn: bool
) -> bool:
    terms, lot = action.terms, deal.lot
    pieces = terms.bundles * lot.pieces
    if buyers_turn:
        return buyer_ok(
            deal.buyer_limit, base_price=terms.base_price, shipping=lot.shipping, pieces=pieces
        )
    return seller_ok(seller_limit, base_price=terms.base_price, pieces=pieces)


def take_step(log: EventLog, deal: Deal, *, clock: FakeClock, settings: Settings) -> bool:
    """One turn of one negotiation. False once it has ended or is waiting for approval."""
    # In firm mode Tommy works to the public firm price. Otherwise, with the privacy layer on,
    # to his floor plus the lot's secret margin.
    seller_limit = guarded(working_limit(deal.seller_limit, deal.lot), settings.privacy)
    negotiation_id, lot, buyer_limit = deal.negotiation_id, deal.lot, deal.buyer_limit
    q = quote(lot, deal.seller, bundles=deal.bundles)
    pieces, rules, t = q.pieces, settings.negotiation, settings.bands

    def buyer_band_of(price: Pence) -> Band:
        return buyer_band(buyer_limit, base_price=price, shipping=lot.shipping, pieces=pieces, t=t)

    def seller_band_of(price: Pence) -> Band:
        return seller_band(seller_limit, base_price=price, pieces=pieces, t=t)

    snap = log.saved(negotiation_id)
    if snap.state in FINAL_STATES or snap.state is NegotiationState.PENDING_APPROVAL:
        return False
    buyers_turn = snap.state in (NegotiationState.OPEN, NegotiationState.COUNTERED)
    actor = Actor.BUYER_AGENT if buyers_turn else Actor.SELLER_AGENT
    history = tuple(e.card for e in log.read(negotiation_id) if e.card is not None)
    view = View(
        lot=deal.buyer_lot if buyers_turn and deal.buyer_lot is not None else lot,
        want=deal.want if buyers_turn else None,
        bundles=deal.bundles,
        list_price=q.base_price,
        history=history,
        rounds_left=rules.max_rounds - snap.cards,
        band=buyer_band_of if buyers_turn else seller_band_of,
        today=clock.now().date(),
        elsewhere=deal.elsewhere() if buyers_turn else (),
        promised=deal.promised if buyers_turn else None,
    )
    offer = view.on_table
    if not buyers_turn and deal.promised is not None and offer is not None:
        # The seller already said yes to this price: code keeps the promise, Tommy isn't asked.
        action: Action = Accept() if offer.base_price >= deal.promised else deal.tommy.decide(view)
    else:
        action = (deal.ralph if buyers_turn else deal.tommy).decide(view)
    within_budget = deal.within_budget
    # The buyer's offers and accepts must fit their budget across all their deals.
    if (
        buyers_turn
        and isinstance(action, (Send, Accept))
        and not within_budget(_order_total(action, view, lot))
    ):
        log.append(
            negotiation_id,
            Move.ESCALATE,
            by=Actor.SYSTEM,
            at=clock.now(),
            reason=EscalationReason.OVER_BUDGET,
        )
    elif isinstance(action, Send) and not _inside_own_limit(
        action, deal, seller_limit, buyers_turn
    ):
        # A card is binding: one past its sender's own limit is never put on the table.
        log.append(
            negotiation_id,
            Move.ESCALATE,
            by=Actor.SYSTEM,
            at=clock.now(),
            reason=EscalationReason.CARD_OUTSIDE_LIMIT,
        )
    elif isinstance(action, Send):
        terms = action.terms
        if not buyers_turn:  # with the privacy layer on, his counter gets shrinking noise
            previous = snap.last_counter.base_price if snap.last_counter else None
            price = jitter(
                terms.base_price,
                limit=seller_limit,
                previous=previous,
                list_price=q.base_price,
                pieces=terms.bundles * lot.pieces,
                lot_id=lot.id,
                card_id=f"{negotiation_id}@{clock.now().isoformat()}",
                rounds_left=view.rounds_left,
                max_rounds=rules.max_rounds,
                rules=settings.privacy,
            )
            terms = terms.model_copy(update={"base_price": price})
        send_card(log, negotiation_id, by=actor, terms=terms, clock=clock, rules=rules)
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
    elif isinstance(action, HandOff):
        log.append(
            negotiation_id, Move.ESCALATE, by=Actor.SYSTEM, at=clock.now(), reason=action.reason
        )
    elif isinstance(action, WalkAway):
        log.append(negotiation_id, Move.WALK_AWAY, by=actor, at=clock.now())
    clock.advance(THINKING)
    return True


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
    within_budget: Callable[[Pence], bool] = lambda _: True,
    buyer_lot: Lot | None = None,
    promised: Pence | None = None,
) -> NegotiationState:
    deal = Deal(
        negotiation_id,
        lot,
        seller,
        want,
        bundles,
        buyer_limit,
        seller_limit,
        ralph,
        tommy,
        within_budget,
        buyer_lot=buyer_lot,
        promised=promised,
    )
    for _ in range(settings.negotiation.max_rounds + 2):
        if not take_step(log, deal, clock=clock, settings=settings):
            break
    return log.saved(negotiation_id).state


def run_parallel(
    log: EventLog, deals: list[Deal], *, clock: FakeClock, settings: Settings
) -> dict[str, NegotiationState]:
    """Several negotiations at once, a turn each in rotation, until all have stopped."""
    live = list(deals)
    for _ in range(settings.negotiation.max_rounds + 2):
        live = [d for d in live if take_step(log, d, clock=clock, settings=settings)]
        if not live:
            break
    return {d.negotiation_id: log.saved(d.negotiation_id).state for d in deals}


def link_buyer_deals(log: EventLog, deals: list[Deal]) -> None:
    """Let each of one buyer's deals see the others: where each stands, in one line."""

    def summary(deal: Deal) -> str:
        snap = log.saved(deal.negotiation_id)
        mine = (
            f"your last offer {snap.last_offer.base_price}" if snap.last_offer else "no offer yet"
        )
        theirs = f"their last counter {snap.last_counter.base_price}" if snap.last_counter else ""
        parts = [f"{deal.lot.title}", str(snap.state), mine, theirs]
        return "; ".join(p for p in parts if p)

    for deal in deals:
        others = [d for d in deals if d is not deal]
        deal.elsewhere = lambda others=others: tuple(summary(d) for d in others)  # type: ignore[misc]
