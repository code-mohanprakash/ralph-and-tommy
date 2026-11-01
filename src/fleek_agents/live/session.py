"""One live negotiation, built from what the seller and the buyer typed, run a turn at a time.

Everything goes through the same code as the rest of the repo: the market tables, matching with
the match gate, ranking, open_negotiation, take_step (the referee), approval, the controls and
the walk-away offer. What's new here is only bookkeeping: who can see each line. The buyer's
screen shows what the buyer could see on Fleek, plus Ralph's own price checks; the seller's
screen likewise for Tommy; Fleek's column shows matching and the referee. Neither side's screen
ever shows the other side's secret.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from fleek_agents.agents.base import Agent, Send
from fleek_agents.config import Settings
from fleek_agents.domain.events import EscalationReason, Event
from fleek_agents.domain.models import (
    Buyer,
    ListingType,
    Lot,
    Market,
    Seller,
    SellMode,
    Want,
)
from fleek_agents.domain.money import Pence
from fleek_agents.domain.rules import quote, walkaway_offer_price
from fleek_agents.domain.state import FINAL_STATES, Move, NegotiationState
from fleek_agents.harness.reader import blind
from fleek_agents.harness.tools import MEANING
from fleek_agents.humans.monitors import watch_list
from fleek_agents.live.forms import FormError, Setup, check_free_text
from fleek_agents.matching.embeddings import HashingEmbedder
from fleek_agents.matching.funnel import bundles_for, possible_deals
from fleek_agents.matching.ranking import rank
from fleek_agents.orchestrator.approval import Approver, NotAsked, approve, pending, reject, settle
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.controls import hand_over, stop
from fleek_agents.orchestrator.offers import send_walkaway_offers
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.run import Deal, take_step
from fleek_agents.room.play import _Watched
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog
from fleek_agents.store.market import hard_filter, load_market
from fleek_agents.store.offers import promised
from fleek_agents.vault.firm import FirmBelowFloor, check_firm_price
from fleek_agents.vault.gate import MatchGate
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate
from fleek_agents.vault.offers import OfferBelowFloor, check_walkaway_offer
from fleek_agents.vault.secret import SecretMoney
from fleek_agents.vault.seed import Secrets

START = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
SELLER_ID, BUYER_ID = "seller-0001", "buyer-0001"

AgentPair = Callable[[], tuple[Agent, Agent]]  # a fresh Ralph and Tommy

NAME = {"ralph": "Ralph", "tommy": "Tommy"}
ENDINGS = {
    NegotiationState.WALKED_AWAY: "No deal: one side walked away.",
    NegotiationState.EXPIRED: "No deal: an offer expired with no answer.",
    NegotiationState.REJECTED_BY_HUMAN: "No deal: a person said no. The stock is back on sale.",
    NegotiationState.STOPPED: "Stopped by a person. No deal.",
    NegotiationState.NEEDS_HUMAN: "Handed to a Fleek account manager to finish by hand.",
    NegotiationState.CLOSED: "Deal closed. The truck leaves.",
    NegotiationState.LOST_TO_OTHER_BUYER: "Another buyer got the lot first.",
}
REFEREE = {
    EscalationReason.CARD_OUTSIDE_LIMIT: "The vault stopped a card past its sender's own limit. "
    "It was never sent. A person takes over.",
    EscalationReason.ACCEPT_OUTSIDE_LIMIT: "The vault refused an accept outside a limit. "
    "A person takes over.",
    EscalationReason.OVER_BUDGET: "That would take the buyer past their budget. A person "
    "takes over.",
    EscalationReason.MODEL_REFUSED: "An agent's AI refused to answer. A person takes over.",
    EscalationReason.TOO_MANY_CORRECTIONS: "An agent kept breaking the format. A person takes "
    "over.",
    EscalationReason.SPEND_CAP: "The AI spending cap for this negotiation was reached. A person "
    "takes over.",
    EscalationReason.ASKED_FOR_A_PERSON: "Handed to a Fleek account manager, as asked.",
}


@dataclass(frozen=True)
class Line:
    """One line on a screen. `side`: who can see it (buyer, seller, both or fleek)."""

    side: str
    who: str  # ralph, tommy, buyer, seller, account_manager, vault, fleek
    text: str
    at: str
    price: int | None = None
    kind: str = "note"  # card, check, note, stop, ask, end


def _clock(at: datetime) -> str:
    return f"{at:%a} {at.day} {at:%b}, {at:%H:%M}"


def _lot_facts(lot: Lot, bundles: int) -> dict[str, Any]:
    return {
        "id": lot.id,
        "title": lot.title,
        "brand": lot.brand,
        "category": lot.category,
        "grade": str(lot.grade),
        "pieces": lot.pieces,
        "bundles": bundles,
        "list_price": str(lot.base_price),
        "shipping": str(lot.shipping),
        "mode": str(lot.sell_mode),
        "firm_price": str(lot.firm_price) if lot.firm_price is not None else None,
        "sell_by": lot.sell_by.isoformat() if lot.sell_by is not None else None,
        "walkaway_offer_pct": lot.walkaway_offer_pct,
    }


def build(setup: Setup, settings: Settings) -> tuple[Market, Secrets]:
    """The market and the vault's mandates. FormError, to the person who typed it, if unusable."""
    check_free_text(setup)
    s, b = setup.seller, setup.buyer
    seller = Seller(
        id=SELLER_ID,
        name=s.name,
        country=s.country,
        quality_score=4.5,
        dispatch_days=2,
        final_say=s.final_say,
    )
    lots, floors = [], {}
    for i, line in enumerate(s.stock):
        lot_id = f"lot-{1001 + i}"
        try:
            lot = Lot(
                id=lot_id,
                seller_id=SELLER_ID,
                title=line.title,
                brand=line.brand,
                category=line.category.lower(),
                grade=line.grade,
                listing_type=ListingType.REPRESENTATIVE,
                pieces=line.pieces,
                available=line.bundles,
                base_price=Pence(line.list_price),
                shipping=Pence(line.shipping),
                description=line.description,
                sell_mode=line.mode,
                firm_price=Pence(line.firm_price)
                if line.mode is SellMode.FIRM and line.firm_price is not None
                else None,
                sell_by=line.sell_by,
                walkaway_offer_pct=line.walkaway_offer_pct,
            )
        except ValueError as error:
            raise FormError(f"{line.title}: {error}") from None
        limit = SellerMandate(SELLER_ID, lot_id, SecretMoney(Pence(line.floor)))
        try:
            if lot.firm_price is not None:
                check_firm_price(limit, lot.firm_price, pieces=lot.pieces)
            check_walkaway_offer(limit, lot, settings.privacy)
        except (FirmBelowFloor, OfferBelowFloor) as error:
            raise FormError(f"{line.title}: {error}") from None
        lots.append(lot)
        floors[lot_id] = limit
    buyer = Buyer(id=BUYER_ID, name=b.name, kind=b.kind, country=b.country, final_say=b.final_say)
    want = Want(
        buyer_id=BUYER_ID,
        category=b.category.lower(),
        brands=b.brands,
        grades=b.grades,
        pieces=b.pieces,
        text=b.notes or f"About {b.pieces} pieces of {b.category.lower()}.",
    )
    market = Market(buyers=(buyer,), sellers=(seller,), lots=tuple(lots), wants=(want,))
    secrets = Secrets(
        buyers={BUYER_ID: BuyerMandate(BUYER_ID, SecretMoney(Pence(b.top_price)))}, lots=floors
    )
    return market, secrets


class LiveSession:
    def __init__(self, setup: Setup, settings: Settings, agents: AgentPair, label: str) -> None:
        self.settings, self.label, self._agents = settings, label, agents
        self.market, self.secrets = build(setup, settings)
        self.buyer, self.seller = self.market.buyers[0], self.market.sellers[0]
        self.want = self.market.wants[0]
        self.lots = {lot.id: lot for lot in self.market.lots}
        # Shown on each side's own screen only. They are the numbers that person typed.
        self._buyer_secret = str(Pence(setup.buyer.top_price))
        self._seller_secrets = {
            f"lot-{1001 + i}": str(Pence(line.floor)) for i, line in enumerate(setup.seller.stock)
        }
        engine = make_engine("sqlite://", shared=True)
        Base.metadata.create_all(engine)
        self.session = Session(engine)
        load_market(self.session, self.market)
        self.log = EventLog(self.session)
        self.clock = FakeClock(START)
        self.lines: list[Line] = []
        self.paused = False
        self.lock = threading.Lock()
        self.gate = MatchGate(settings.match_gate, settings.privacy)
        self.lot: Lot | None = None
        self.bundles = 0
        self.nid: str | None = None
        self.deal: Deal | None = None
        self.watched: dict[str, _Watched] = {}
        self.matching: list[dict[str, Any]] = []
        self._match()

    # Building

    def _say(self, side: str, who: str, text: str, *, at: str | None = None, **extra: Any) -> None:
        self.lines.append(Line(side, who, text, at or _clock(self.clock.now()), **extra))

    def _match(self) -> None:
        passed = {lot.id for lot in hard_filter(self.session, self.want)}
        gate = self.gate if self.settings.match_gate.on else None
        found = possible_deals(
            self.session, self.market, self.secrets, self.want, gate=gate, today=START.date()
        )
        possible = {c.lot.id for c in found}
        self.matching = [
            {
                "title": lot.title,
                "passed_filters": lot.id in passed,
                "possible": (lot.id in possible) if lot.id in passed else None,
            }
            for lot in self.market.lots
        ]
        self._say(
            "fleek",
            "fleek",
            f"Matching: {len(passed)} of {len(self.lots)} lots pass the filters; the vault says "
            f"a price could work for {len(possible)}. It answers yes or no, never a number.",
        )
        top = rank(self.want, found, HashingEmbedder(), top=1)
        if not top:
            self._say("both", "fleek", "No lot can work for both sides, so no agent is called.")
            return
        self.lot = top[0].lot
        self.bundles = bundles_for(self.want, self.lot)
        self._say("buyer", "fleek", f"Fleek found a lot for you: {self.lot.title}.")
        self._say("seller", "fleek", f"A buyer is interested in {self.lot.title}.")
        self._open()

    def _open(self, *, offer: Pence | None = None, nid: str | None = None) -> None:
        assert self.lot is not None
        self.nid = nid or open_negotiation(
            self.log,
            buyer_id=BUYER_ID,
            lot_id=self.lot.id,
            clock=self.clock,
            rules=self.settings.negotiation,
        )
        ralph, tommy = self._agents()
        self.watched = {"ralph": _Watched(ralph), "tommy": _Watched(tommy)}
        self.deal = Deal(
            self.nid,
            self.lot,
            self.seller,
            self.want,
            self.bundles,
            self.secrets.buyers[BUYER_ID],
            self.secrets.lots[self.lot.id],
            self.watched["ralph"],
            self.watched["tommy"],
            buyer_lot=blind(self.lot),
            promised=offer,
        )

    # Running

    @property
    def state(self) -> NegotiationState | None:
        return self.log.state(self.nid) if self.nid is not None else None

    def step(self) -> bool:
        """One turn. False when there's nothing to do (paused, waiting, or over)."""
        if self.deal is None or self.paused or self.nid is None:
            return False
        nid = self.nid
        if self.state in FINAL_STATES or self.state is NegotiationState.PENDING_APPROVAL:
            return False
        before, when = len(self.log.read(nid)), _clock(self.clock.now())
        for w in self.watched.values():
            w.action, w.asked = None, []
        take_step(self.log, self.deal, clock=self.clock, settings=self.settings)
        new = self.log.read(nid)[before:]
        for who, w in self.watched.items():
            side = "buyer" if who == "ralph" else "seller"
            for asked in w.asked:
                self._say(
                    side,
                    who,
                    f"{NAME[who]} checked {asked.price}: {MEANING[asked.band]}.",
                    at=when,
                    price=asked.price.value,
                    kind="check",
                )
            if w.action is not None:
                self._tell(who, w.action, new, when)
        self._after()
        return True

    def _tell(self, who: str, action: Any, events: list[Event], when: str) -> None:
        side = "buyer" if who == "ralph" else "seller"
        for e in events:
            if e.card is not None:
                verb = "offers" if e.move is Move.OFFER else "counters with"
                self._say(
                    "both",
                    who,
                    f"{NAME[who]} {verb} {e.card.base_price} a piece.",
                    price=e.card.base_price.value,
                    at=when,
                    kind="card",
                )
            elif e.move is Move.ACCEPT:
                self._say("both", who, f"{NAME[who]} accepts.", kind="card", at=when)
            elif e.move is Move.WALK_AWAY:
                self._say("both", who, f"{NAME[who]} walks away.", kind="card", at=when)
            elif e.move is Move.ESCALATE and e.reason is not None:
                if e.reason is EscalationReason.CARD_OUTSIDE_LIMIT and isinstance(action, Send):
                    limit = "top price" if who == "ralph" else "floor"
                    self._say(
                        side,
                        "vault",
                        f"{NAME[who]} tried to send {action.terms.base_price}, past your "
                        f"{limit}. The vault stopped it; the other side never saw it.",
                        at=when,
                        kind="stop",
                    )
                self._say("both", "vault", REFEREE[e.reason], kind="stop", at=when)

    def _after(self) -> None:
        assert self.nid is not None and self.lot is not None
        state = self.state
        if state is NegotiationState.PENDING_APPROVAL:
            crowded = self.gate.crowded_lots(START.date(), accounts=self._crowd)
            flagged = any(w.buyer_id == BUYER_ID for w in watch_list(self.log, self.lots, crowded))
            agreed = self.log.saved(self.nid).agreed
            settle(
                self.log,
                self.nid,
                lots=self.lots,
                rules=self.settings.approval,
                at=self.clock.now(),
                buyer=self.buyer,
                seller=self.seller,
                flagged=flagged,
            )
            if agreed is not None:
                self._say(
                    "both",
                    "fleek",
                    f"Agreed at {agreed.base_price} a piece. The vault checked it's inside both "
                    "limits, and the stock is held.",
                    kind="end",
                )
            for w in pending(self.log, self.lots, self.settings.approval):
                for ask in w.asks:
                    side = {"buyer": "buyer", "seller": "seller"}.get(ask.who, "fleek")
                    self._say(side, ask.who, f"Waiting for your OK: {ask.why}.", kind="ask")
            if self.state is NegotiationState.CLOSED:
                self._say("both", "fleek", "Approved by the rule. " + ENDINGS[self.state])
            return
        if state is NegotiationState.WALKED_AWAY and self.lot.walkaway_offer_pct is not None:
            sent = send_walkaway_offers(
                self.log, self.lot, clock=self.clock, rules=self.settings.negotiation
            )
            if BUYER_ID in sent:
                self._say("both", "fleek", ENDINGS[state], kind="end")
                price = Pence(promised(self.session, sent[BUYER_ID]) or 0)
                self._say(
                    "both",
                    "seller",
                    f"The seller's standing offer goes out: {self.lot.walkaway_offer_pct}% off, "
                    f"{price} a piece. Offer it and it's accepted.",
                    kind="ask",
                )
                self._open(offer=price, nid=sent[BUYER_ID])
                return
        if state in ENDINGS:
            self._say("both", "fleek", ENDINGS[state], kind="end")

    @property
    def _crowd(self) -> int:
        return self.settings.match_gate.crowd_accounts

    # People

    def control(self, action: str, side: str) -> None:
        if self.nid is None:
            raise FormError("There's no negotiation to control.")
        who = "The buyer" if side == "buyer" else "The seller"
        if action == "pause":
            self.paused = True
            self._say("both", side, f"{who} paused it. Nothing moves until they resume.")
        elif action == "resume":
            self.paused = False
            self._say("both", side, f"{who} resumed it.")
        elif action == "stop":
            stop(self.log, self.nid, at=self.clock.now())
            self._say("both", side, f"{who} stopped it. No deal.", kind="end")
        elif action == "hand_over":
            hand_over(self.log, self.nid, at=self.clock.now())
            self._say("both", side, f"{who} handed it to a Fleek account manager.", kind="end")
        else:
            raise FormError(f"Unknown action: {action}")

    def decide(self, who: str, decision: str) -> None:
        if self.nid is None:
            raise FormError("There's nothing to decide.")
        try:
            by = Approver(who)
        except ValueError:
            raise FormError(f"Unknown person: {who}") from None
        try:
            if decision == "approve":
                approve(self.log, self.nid, at=self.clock.now(), by=by)
                say = "said yes"
            elif decision == "reject":
                reject(self.log, self.nid, at=self.clock.now(), by=by)
                say = "said no"
            else:
                raise FormError("Decision must be approve or reject.")
        except NotAsked as error:
            raise FormError(str(error)) from None
        name = by.replace("_", " ")
        self._say("both", str(by), f"The {name} {say}.")
        state = self.state
        if state in ENDINGS:
            self._say("both", "fleek", ENDINGS[state], kind="end")

    # What each screen shows

    def _asked(self, who: Approver) -> bool:
        return any(
            a.who is who
            for w in pending(self.log, self.lots, self.settings.approval)
            if w.negotiation_id == self.nid
            for a in w.asks
        )

    def _visible(self, side: str) -> list[dict[str, Any]]:
        return [
            line.__dict__
            for line in self.lines
            if line.side == side or (line.side == "both" and side != "fleek")
        ]

    def view(self) -> dict[str, Any]:
        state = self.state
        lot = _lot_facts(self.lot, self.bundles) if self.lot is not None else None
        over = state is None or state in FINAL_STATES
        q = quote(self.lot, self.seller, bundles=self.bundles) if self.lot else None
        return {
            "agents": self.label,
            "time": _clock(self.clock.now()),
            "state": str(state) if state is not None else "no_match",
            "over": over,
            "waiting": state is NegotiationState.PENDING_APPROVAL,
            "paused": self.paused,
            "lot": lot,
            "list_price_for_order": str(q.base_price) if q else None,
            "buyer": {
                "name": self.buyer.name,
                "secret": self._buyer_secret,
                "final_say": str(self.buyer.final_say),
                "ralph_sees_description": blind(self.lot).description if self.lot else None,
                "description": self.lot.description if self.lot else None,
                "lines": self._visible("buyer"),
                "asked": self._asked(Approver.BUYER),
            },
            "seller": {
                "name": self.seller.name,
                "secret": self._seller_secrets.get(self.lot.id) if self.lot else None,
                "final_say": str(self.seller.final_say),
                "lines": self._visible("seller"),
                "asked": self._asked(Approver.SELLER),
            },
            "fleek": {
                "matching": self.matching,
                "lines": self._visible("fleek"),
                "asked": self._asked(Approver.ACCOUNT_MANAGER),
                "watch": [
                    {"buyer": w.buyer_id, "why": w.why}
                    for w in watch_list(
                        self.log,
                        self.lots,
                        self.gate.crowded_lots(START.date(), accounts=self._crowd),
                    )
                ],
                "offer_price": (
                    str(walkaway_offer_price(self.lot)) if self.lot is not None else None
                ),
            },
        }
