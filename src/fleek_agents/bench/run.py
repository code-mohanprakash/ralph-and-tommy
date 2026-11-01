"""Run a suite: every scenario, k runs each, in a fixed order (so replays line up)."""

from collections.abc import Callable, Sequence

from fleek_agents.bench.episode import AgentPair, Episode, run_episode
from fleek_agents.bench.scenarios import Scenario
from fleek_agents.bench.score import Summary
from fleek_agents.config import Settings

CORE_SCENARIOS = 40


def run_suite(
    scenarios: Sequence[Scenario],
    pair: AgentPair,
    settings: Settings,
    *,
    runs: int = 1,
    label: str = "control",
    progress: Callable[[str], None] = lambda _: None,
) -> list[Episode]:
    episodes = []
    for scenario in scenarios:
        for run in range(runs):
            progress(f"{label} {scenario.key} run {run + 1}")
            episodes.append(run_episode(scenario, pair, settings, label=label, run=run))
    return episodes


def summary_rows(summary: Summary) -> list[tuple[str, str]]:
    """The summary as (score, value with 95% interval) rows, for the CLI and the docs."""
    return [
        ("Loyal success", summary.loyal_success.as_percent()),
        ("Deal rate, where a deal works", summary.deal_rate.as_percent()),
        ("Buyer's share of the room", summary.buyer_share.as_percent()),
        ("Canary seen (secret in model text)", summary.canary_rate.as_percent()),
        (
            "Deals outside a limit",
            f"{summary.breaches} of {summary.episodes}"
            + (f" (95% upper bound {summary.breach_bound:.1%})" if summary.breaches == 0 else ""),
        ),
        ("Every run inside the limits (pass^k)", summary.no_breach_every_run.as_percent()),
    ]
