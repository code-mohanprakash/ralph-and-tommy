"""Who negotiates in the Deal Room: the scripted agents, or Claude.

Claude runs two ways:
- replayed from a recording kept in this repo, one per scenario: no key, no internet, no cost,
  and the same answers every time;
- live, with the key in .env: any numbers, at about half a US cent a negotiation with Haiku,
  capped per negotiation by market.toml.

A recording answers only the exact requests it saw, so replay works for the five scenarios and
says so clearly for anything else.
"""

from collections.abc import Callable
from pathlib import Path

from fleek_agents.agents.base import Agent
from fleek_agents.agents.claude import ClaudeAgent
from fleek_agents.agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.config import Settings
from fleek_agents.llm.budget import BudgetedClient, Ledger
from fleek_agents.llm.client import LiveClient, LLMClient
from fleek_agents.llm.replay import RecordingClient, ReplayClient
from fleek_agents.room.play import RoomRun, run_room
from fleek_agents.room.scenario import SCENARIOS, RoomInput

RECORDINGS = Path(__file__).parent / "recordings"
MODEL_NAMES = {"claude-haiku-5-5": "Claude Haiku 5.5", "claude-sonnet-5-5": "Claude Sonnet 5.5"}

AgentPair = Callable[[RoomInput], tuple[Agent, Agent]]  # a fresh Ralph and Tommy for each run


class NoRecording(Exception):
    """Replay was asked for numbers that were never recorded."""


def cassette(model: str, key: str) -> Path:
    return RECORDINGS / f"{model}_{key}.jsonl"


def _claude(client: LLMClient, model: str) -> tuple[Agent, Agent]:
    return (
        ClaudeAgent(client, model=model, prompt="ralph"),
        ClaudeAgent(client, model=model, prompt="tommy"),
    )


def scripted() -> AgentPair:
    return lambda _room: (ScriptedRalph(), ScriptedTommy())


def replayed(model: str) -> AgentPair:
    def pair(room: RoomInput) -> tuple[Agent, Agent]:
        key = next((x.key for x in SCENARIOS if x.room == room), None)
        if key is None or not cassette(model, key).exists():
            raise NoRecording(
                f"There's no recording of {MODEL_NAMES.get(model, model)} for these numbers. "
                "Pick a scenario button, or restart with --live to ask Claude now (needs the "
                "API key in .env)."
            )
        return _claude(ReplayClient(cassette(model, key)), model)  # a fresh one: answers pop

    return pair


def live(model: str, settings: Settings) -> AgentPair:
    def pair(_room: RoomInput) -> tuple[Agent, Agent]:
        ledger = Ledger(cap_microcents=settings.spending.negotiation_cap_cents * 1_000_000)
        return _claude(BudgetedClient(LiveClient(), ledger, settings.spending), model)

    return pair


def record(model: str, settings: Settings) -> list[tuple[str, RoomRun]]:
    """Run every scenario against Claude once and keep each run's calls as its recording."""
    runs = []
    total = Ledger(cap_microcents=settings.spending.run_cap_cents * 1_000_000)
    for scenario in SCENARIOS:
        one = Ledger(
            cap_microcents=settings.spending.negotiation_cap_cents * 1_000_000, parent=total
        )
        client = RecordingClient(
            BudgetedClient(LiveClient(), one, settings.spending), cassette(model, scenario.key)
        )
        ralph, tommy = _claude(client, model)
        runs.append(
            (scenario.key, run_room(scenario.room, ralph=ralph, tommy=tommy, settings=settings))
        )
    return runs
