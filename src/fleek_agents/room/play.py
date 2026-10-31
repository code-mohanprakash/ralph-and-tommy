"""Run the Deal Room's negotiation with the real code, noting what each agent asked the vault.

Everything goes through the same functions as `fleek negotiate`: the filters, the vault's "could
any price work?", ranking, open_negotiation, take_step (the referee), and the approval rule. The
only addition is a wrapper on each agent that writes down the band checks it makes, so the page
can show them. It passes every answer through unchanged.
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from fleek_agents.agents.base import Action, Agent, Send, View
from fleek_agents.config import Settings
from fleek_agents.domain.bands import Band
from fleek_agents.domain.events import Event
from fleek_agents.domain.models import Lot, Market
from fleek_agents.domain.money import Pence
from fleek_agents.domain.rules import quote
from fleek_agents.domain.state import NegotiationState
from fleek_agents.matching.embeddings import HashingEmbedder
from fleek_agents.matching.funnel import bundles_for, possible_deals
from fleek_agents.matching.ranking import rank
from fleek_agents.orchestrator.approval import pending, settle
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.run import Deal, take_step
from fleek_agents.room.scenario import RoomInput, room_market, room_secrets
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog
from fleek_agents.store.market import hard_filter, load_market
from fleek_agents.vault.checks import buyer_ok, seller_ok
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate

START = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Asked:
    """One band check: the price an agent asked about, and the one word it got back."""

    price: Pence
    band: Band


@dataclass(frozen=True)
class Turn:
    who: str  # "ralph" or "tommy"
    asked: tuple[Asked, ...]
    action: Action
    events: tuple[Event, ...]  # what the referee recorded for this turn


@dataclass(frozen=True)
class Checked:
    """What matching decided about one warehouse's lot."""

    lot: Lot
    passed_filters: bool
    possible: bool | None  # the vault's yes/no; None when the filters already dropped the lot


@dataclass(frozen=True)
class CardLimits:
    """The secret limits as card prices: the audience view only. No agent is ever given these."""

    buyer_highest: Pence | None  # the highest card price the shop can pay, up to the list
    # price (the search stops there); None: not even 0p
    seller_lowest: Pence | None  # the lowest card price the warehouse takes; None: not even list


@dataclass
class RoomRun:
    room: RoomInput
    market: Market
    log: EventLog
    checked: tuple[Checked, ...]
    lot: Lot | None = None  # the lot negotiated; None when matching found nothing
    bundles: int = 0
    negotiation_id: str | None = None
    turns: list[Turn] = field(default_factory=list)
    final: NegotiationState | None = None
    why_waiting: str | None = None  # why a person must approve, when one must
    limits: CardLimits = CardLimits(None, None)


class _Watched:
    """An agent, plus a note of each band check it makes. It changes nothing it decides."""

    def __init__(self, inner: Agent) -> None:
        self._inner = inner
        self.asked: list[Asked] = []
        self.action: Action | None = None

    def decide(self, view: View) -> Action:
        self.asked = []

        def band(price: Pence) -> Band:
            answer = view.band(price)
            self.asked.append(Asked(price, answer))
            return answer

        self.action = self._inner.decide(replace(view, band=band))
        return self.action


class BreaksARule:
    """A Tommy broken on purpose: his second counter is half of Ralph's last offer.

    The slip a model can make under pressure. In the recorded probing-bot run, Claude Tommy did
    try to counter below his floor (`fleek safety`). Tommy doesn't know his floor, so he can't
    aim below it; half of Ralph's offer is far enough down to show the vault refusing.
    """

    def __init__(self, inner: Agent) -> None:
        self._inner, self._counters = inner, 0

    def decide(self, view: View) -> Action:
        action = self._inner.decide(view)
        if isinstance(action, Send) and view.on_table is not None:
            self._counters += 1
            if self._counters == 2:
                half = Pence(view.on_table.base_price.value // 2 // 5 * 5)
                return Send(terms=action.terms.model_copy(update={"base_price": half}))
        return action


def card_limits(
    buyer: BuyerMandate, seller: SellerMandate, lot: Lot, *, list_price: Pence, pieces: int
) -> CardLimits:
    """Search the card prices from 0p to the list price with the vault's own yes/no checks."""

    def first(ok: list[bool]) -> int | None:
        return next((i for i, yes in enumerate(ok) if yes), None)

    prices = range(list_price.value + 1)
    seller_says = [seller_ok(seller, base_price=Pence(p), pieces=pieces) for p in prices]
    buyer_says = [
        buyer_ok(buyer, base_price=Pence(p), shipping=lot.shipping, pieces=pieces) for p in prices
    ]
    lowest = first(seller_says)
    highest = next((p for p in reversed(prices) if buyer_says[p]), None)
    return CardLimits(
        buyer_highest=None if highest is None else Pence(highest),
        seller_lowest=None if lowest is None else Pence(lowest),
    )


def run_room(room: RoomInput, *, ralph: Agent, tommy: Agent, settings: Settings) -> RoomRun:
    market = room_market(room.pairs)
    secrets = room_secrets(market, room)
    want = market.wants[0]
    sellers = {s.id: s for s in market.sellers}

    engine = make_engine("sqlite://", shared=True)  # the server reads it again on approve
    Base.metadata.create_all(engine)
    session = Session(engine)
    load_market(session, market)
    log = EventLog(session)

    passed = {lot.id for lot in hard_filter(session, want)}
    candidates = possible_deals(session, market, secrets, want)
    possible = {c.lot.id for c in candidates}
    checked = tuple(
        Checked(lot, lot.id in passed, (lot.id in possible) if lot.id in passed else None)
        for lot in market.lots
    )
    run = RoomRun(room=room, market=market, log=log, checked=checked)
    top = rank(want, candidates, HashingEmbedder())
    if not top:
        return run

    lot = run.lot = top[0].lot
    run.bundles = bundles_for(want, lot)
    seller = sellers[lot.seller_id]
    q = quote(lot, seller, bundles=run.bundles)
    buyer_limit, seller_limit = secrets.buyers[want.buyer_id], secrets.lots[lot.id]
    run.limits = card_limits(
        buyer_limit, seller_limit, lot, list_price=q.base_price, pieces=q.pieces
    )

    clock = FakeClock(START)
    nid = run.negotiation_id = open_negotiation(
        log, buyer_id=want.buyer_id, lot_id=lot.id, clock=clock, rules=settings.negotiation
    )
    if room.tommy_breaks_a_rule:
        tommy = BreaksARule(tommy)
    watched = {"ralph": _Watched(ralph), "tommy": _Watched(tommy)}
    deal = Deal(
        nid,
        lot,
        seller,
        want,
        run.bundles,
        buyer_limit,
        seller_limit,
        watched["ralph"],
        watched["tommy"],
    )
    for _ in range(settings.negotiation.max_rounds + 2):
        before = len(log.read(nid))
        for w in watched.values():
            w.action = None
        going = take_step(log, deal, clock=clock, settings=settings)
        for who, w in watched.items():
            if w.action is not None:
                events = tuple(log.read(nid)[before:])
                run.turns.append(Turn(who, tuple(w.asked), w.action, events))
        if not going:
            break

    rules = settings.approval
    if room.regular_buyer:  # a shop that has closed deals before: only the amount rule applies
        rules = rules.model_copy(update={"first_deals_by_person": 0})
    lots = {x.id: x for x in market.lots}
    run.final = settle(log, nid, lots=lots, rules=rules, at=clock.now())
    waiting = [w for w in pending(log, lots, rules) if w.negotiation_id == nid]
    run.why_waiting = waiting[0].why if waiting else None
    return run
