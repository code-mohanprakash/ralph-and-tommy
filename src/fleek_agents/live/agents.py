"""Who negotiates in the live demo: scripted agents, or Claude (live, recorded, or replayed).

Claude live needs the key in .env and costs about half a US cent a negotiation with Haiku,
capped per run by market.toml. Replay answers only the exact requests it saw, so it covers the
ready-made onboarding (the preset) and says so for anything else.
"""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from fleek_agents.agents.base import Agent
from fleek_agents.agents.claude import ClaudeAgent
from fleek_agents.agents.rerank import Reranked, rerank
from fleek_agents.config import Settings
from fleek_agents.domain.models import Seller, Want
from fleek_agents.live.session import AgentPair
from fleek_agents.llm.budget import BudgetedClient, Ledger
from fleek_agents.llm.client import LiveClient, LLMClient
from fleek_agents.llm.replay import RecordingClient, ReplayClient
from fleek_agents.matching.score import Scored
from fleek_agents.scripted import ScriptedRalph, ScriptedTommy

RECORDINGS = Path(__file__).parent / "recordings"


def cassette(model: str) -> Path:
    return RECORDINGS / f"{model}_preset.jsonl"


class ClaudePair:
    """Fresh Claude Ralph and Tommy for each negotiation, and Ralph's re-rank of the top lots."""

    def __init__(self, client: LLMClient, model: str) -> None:
        self.client, self.model = client, model

    def __call__(self) -> tuple[Agent, Agent]:
        return (
            ClaudeAgent(self.client, model=self.model, prompt="ralph"),
            ClaudeAgent(self.client, model=self.model, prompt="tommy"),
        )

    def rerank(
        self, want: Want, ranked: Sequence[Scored], sellers: Mapping[str, Seller]
    ) -> Reranked:
        return rerank(self.client, model=self.model, want=want, ranked=ranked, sellers=sellers)


def _claude(client: LLMClient, model: str) -> AgentPair:
    return ClaudePair(client, model)


def scripted() -> AgentPair:
    return lambda: (ScriptedRalph(), ScriptedTommy())


def live(model: str, settings: Settings) -> Callable[[], AgentPair]:
    def fresh() -> AgentPair:
        ledger = Ledger(cap_microcents=settings.spending.run_cap_cents * 1_000_000)
        return _claude(BudgetedClient(LiveClient(), ledger, settings.spending), model)

    return fresh


def replayed(model: str) -> Callable[[], AgentPair]:
    return lambda: _claude(ReplayClient(cassette(model)), model)  # a fresh one: answers pop


def recording(model: str, settings: Settings) -> AgentPair:
    ledger = Ledger(cap_microcents=settings.spending.run_cap_cents * 1_000_000)
    client = RecordingClient(
        BudgetedClient(LiveClient(), ledger, settings.spending), cassette(model)
    )
    return _claude(client, model)
