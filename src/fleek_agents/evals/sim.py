"""The market simulation: many buyers, each matched and negotiated, then measured.

Every buyer in the sample goes through the real pipeline: the matching funnel, their top-ranked
lot, a negotiation under every rule. All buyers share one database, so two can want the same
one-of-one lot, as on Fleek. Gains are measured against the secret limits here, in the harness,
and only totals are reported: how much each side kept between the agreed price and its limit.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from fleek_agents.agents.base import Agent
from fleek_agents.agents.claude import ClaudeAgent
from fleek_agents.config import Settings
from fleek_agents.domain.fees import buyer_pays, seller_receives
from fleek_agents.domain.models import Market
from fleek_agents.domain.state import NegotiationState
from fleek_agents.llm.budget import cost_microcents
from fleek_agents.matching.embeddings import HashingEmbedder
from fleek_agents.matching.funnel import bundles_for, possible_deals
from fleek_agents.matching.ranking import rank
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.run import run_negotiation
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog
from fleek_agents.store.market import load_market
from fleek_agents.vault.seed import Secrets

START = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


@dataclass
class Result:
    buyer_id: str
    state: NegotiationState | None  # None: no lot could work for this buyer
    cards: int = 0
    discount_pct: float | None = None  # agreed base price below the list price
    buyer_gain: int = 0  # pence the buyer kept under their limit
    seller_gain: int = 0  # pence the seller got above their floor
    calls: int = 0
    cost_microcents: int = 0


@dataclass
class Summary:
    agents: str
    results: list[Result] = field(default_factory=list)

    @property
    def negotiated(self) -> list[Result]:
        return [r for r in self.results if r.state is not None]

    @property
    def deals(self) -> list[Result]:
        return [r for r in self.results if r.state is NegotiationState.PENDING_APPROVAL]

    def line(self) -> dict[str, str]:
        n, deals = self.negotiated, self.deals
        gains = sum(r.buyer_gain + r.seller_gain for r in deals)
        buyer_share = sum(r.buyer_gain for r in deals) / gains if gains else 0.0
        cost = sum(r.cost_microcents for r in self.results)
        return {
            "agents": self.agents,
            "buyers": str(len(self.results)),
            "negotiated": str(len(n)),
            "deals": f"{len(deals)} ({len(deals) / len(n):.0%})" if n else "0",
            "avg cards": f"{sum(r.cards for r in n) / len(n):.1f}" if n else "-",
            "avg discount from list": (
                f"{sum(r.discount_pct or 0 for r in deals) / len(deals):.1f}%" if deals else "-"
            ),
            "buyer's share of the gains": f"{buyer_share:.0%}" if gains else "-",
            "AI cost per deal": f"{cost / len(deals) / 1e6:.2f}¢" if deals and cost else "0",
        }


def simulate(
    market: Market,
    secrets: Secrets,
    buyer_ids: Sequence[str],
    *,
    agents: str,
    ralph: Callable[[], Agent],
    tommy: Callable[[], Agent],
    settings: Settings | None = None,
) -> Summary:
    settings = settings or Settings()
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    load_market(session, market)
    log, clock = EventLog(session), FakeClock(START)
    sellers = {s.id: s for s in market.sellers}
    wants = {w.buyer_id: w for w in market.wants}
    summary = Summary(agents=agents)
    for buyer_id in buyer_ids:
        want = wants[buyer_id]
        top = rank(want, possible_deals(session, market, secrets, want), HashingEmbedder(), top=1)
        if not top:
            summary.results.append(Result(buyer_id, None))
            continue
        lot, bundles = top[0].lot, bundles_for(want, top[0].lot)
        buyer_agent, seller_agent = ralph(), tommy()
        nid = open_negotiation(
            log, buyer_id=buyer_id, lot_id=lot.id, clock=clock, rules=settings.negotiation
        )
        state = run_negotiation(
            log,
            nid,
            lot=lot,
            seller=sellers[lot.seller_id],
            want=want,
            bundles=bundles,
            buyer_limit=secrets.buyers[buyer_id],
            seller_limit=secrets.lots[lot.id],
            ralph=buyer_agent,
            tommy=seller_agent,
            clock=clock,
            settings=settings,
        )
        snap = log.saved(nid)
        result = Result(buyer_id, state, cards=snap.cards)
        if snap.agreed is not None and state is NegotiationState.PENDING_APPROVAL:
            pieces = snap.agreed.bundles * lot.pieces
            price = snap.agreed.base_price
            paid = buyer_pays(base_price=price, shipping=lot.shipping, pieces=pieces).total
            net = seller_receives(base_price=price, pieces=pieces).net
            max_total = secrets.buyers[buyer_id].max_per_piece.reveal().times(pieces)
            floor_total = secrets.lots[lot.id].floor_per_piece.reveal().times(pieces)
            result.discount_pct = 100 * (1 - price.value / top[0].quote.base_price.value)
            result.buyer_gain = max_total.value - paid.value
            result.seller_gain = net.value - floor_total.value
        for agent in (buyer_agent, seller_agent):
            if isinstance(agent, ClaudeAgent):
                for turn in agent.turns:
                    result.calls += turn.calls
                    result.cost_microcents += cost_microcents(
                        agent.model, turn.input_tokens, turn.output_tokens, settings.spending
                    )
        summary.results.append(result)
    return summary
