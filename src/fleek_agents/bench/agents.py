"""Who plays on the bench: the scripted agents, or Claude replayed, live or recorded.

Claude runs are recorded once per suite into one compressed cassette and replayed for free
after that. A replay answers only the exact requests it saw, so changing a prompt, a scenario or
the order of runs makes it fail loudly instead of replaying the wrong answers.
"""

from pathlib import Path

from fleek_agents.agents.base import Agent
from fleek_agents.agents.claude import ClaudeAgent
from fleek_agents.bench.episode import AgentPair, TapClient
from fleek_agents.bench.scenarios import Scenario
from fleek_agents.config import Settings
from fleek_agents.llm.budget import BudgetedClient, Ledger
from fleek_agents.llm.client import LiveClient, LLMClient
from fleek_agents.llm.replay import RecordingClient, ReplayClient
from fleek_agents.scripted import ScriptedRalph, ScriptedTommy

RECORDINGS = Path(__file__).parent / "recordings"


def scripted() -> AgentPair:
    def pair(_scenario: Scenario, _run: int) -> tuple[Agent, Agent, list[TapClient]]:
        return ScriptedRalph(), ScriptedTommy(), []

    return pair


def cassette(model: str, suite: str) -> Path:
    return RECORDINGS / f"{model}_{suite}.jsonl.gz"


def claude_client(
    model: str, suite: str, settings: Settings, *, live: bool, record: bool
) -> LLMClient:
    """One client for a whole suite: replayed by default, live (and maybe recorded) on request."""
    if not live:
        return ReplayClient(cassette(model, suite))
    run_ledger = Ledger(cap_microcents=settings.spending.run_cap_cents * 1_000_000)
    budgeted = BudgetedClient(LiveClient(), run_ledger, settings.spending)
    return RecordingClient(budgeted, cassette(model, suite)) if record else budgeted


def claude_ralph(client: LLMClient, model: str, tommy: Agent | None = None) -> AgentPair:
    """Claude as the buyer, against scripted Tommy unless another seller is given."""

    def pair(_scenario: Scenario, _run: int) -> tuple[Agent, Agent, list[TapClient]]:
        tap = TapClient(client)
        return ClaudeAgent(tap, model=model, prompt="ralph"), tommy or ScriptedTommy(), [tap]

    return pair


def claude_both(client: LLMClient, model: str) -> AgentPair:
    def pair(_scenario: Scenario, _run: int) -> tuple[Agent, Agent, list[TapClient]]:
        tap = TapClient(client)
        ralph = ClaudeAgent(tap, model=model, prompt="ralph")
        return ralph, ClaudeAgent(tap, model=model, prompt="tommy"), [tap]

    return pair
