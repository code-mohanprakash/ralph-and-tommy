"""Run one scenario between two agents, and keep everything the scorer needs.

A TapClient sits between a Claude agent and the API (live or replayed) and keeps every request
and response as text. The canary check searches that text: if a secret limit ever went into a
prompt or came out of the model, it shows up there.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from anthropic.types.beta import BetaMessage
from sqlalchemy.orm import Session

from fleek_agents.agents.base import Agent
from fleek_agents.bench.scenarios import Scenario
from fleek_agents.config import Settings
from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.models import Lot
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import OfferCard
from fleek_agents.domain.state import NegotiationState
from fleek_agents.llm.client import LLMClient
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.run import run_negotiation
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.deals import put_on_sale
from fleek_agents.store.events import EventLog

START = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
AGREED = {NegotiationState.PENDING_APPROVAL, NegotiationState.CLOSED}


class TapClient:
    """Passes every call through and keeps the request and the response as text."""

    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner
        self.seen: list[str] = []

    def create(self, **params: Any) -> BetaMessage:
        self.seen.append(_text(params))
        response = self._inner.create(**params)
        self.seen.append(response.model_dump_json())
        return response


def _text(params: dict[str, Any]) -> str:
    return json.dumps(params, default=str, ensure_ascii=False)


@dataclass
class Episode:
    scenario: Scenario
    label: str  # e.g. "control", or a tactic's name
    run: int
    state: NegotiationState
    price: Pence | None  # the agreed base price per piece, if they agreed
    offers: list[Pence]  # the buyer's cards, in order
    counters: list[Pence]  # the seller's cards, in order
    escalated: EscalationReason | None
    seen: list[str] = field(default_factory=list)  # every model request and response, as text
    cards: list[OfferCard] = field(default_factory=list)  # every card, oldest first

    @property
    def agreed(self) -> bool:
        return self.state in AGREED


AgentPair = Callable[[Scenario, int], tuple[Agent, Agent, list[TapClient]]]


def run_episode(
    scenario: Scenario,
    pair: AgentPair,
    settings: Settings,
    *,
    label: str = "control",
    run: int = 0,
    buyer_lot: Lot | None = None,
) -> Episode:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        # Each run starts a day later, as a repeat visit would after the cooldown.
        log, clock = EventLog(session), FakeClock(START + timedelta(days=run))
        put_on_sale(session, scenario.lot.id, bundles=1)
        nid = open_negotiation(
            log,
            buyer_id=scenario.want.buyer_id,
            lot_id=scenario.lot.id,
            clock=clock,
            rules=settings.negotiation,
        )
        ralph, tommy, taps = pair(scenario, run)
        state = run_negotiation(
            log,
            nid,
            lot=scenario.lot,
            seller=scenario.seller,
            want=scenario.want,
            bundles=1,
            buyer_limit=scenario.buyer,
            seller_limit=scenario.seller_limit,
            ralph=ralph,
            tommy=tommy,
            clock=clock,
            settings=settings,
            buyer_lot=buyer_lot,
        )
        snap = log.saved(nid)
        cards = [e.card for e in log.read(nid) if e.card is not None]
        return Episode(
            scenario=scenario,
            label=label,
            run=run,
            state=state,
            price=snap.agreed.base_price if snap.agreed is not None else None,
            offers=[c.base_price for c in cards if c.from_role == "buyer"],
            counters=[c.base_price for c in cards if c.from_role == "seller"],
            escalated=snap.escalated_because,
            seen=[text for tap in taps for text in tap.seen],
            cards=cards,
        )
