import gzip
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from typer.testing import CliRunner

from fleek_agents.bench.agents import scripted
from fleek_agents.bench.episode import TapClient, run_episode
from fleek_agents.bench.run import run_suite
from fleek_agents.bench.scenarios import PIECES, generate
from fleek_agents.bench.score import breach, buyer_share, canary_seen, loyal, summarise
from fleek_agents.cli import app
from fleek_agents.config import Settings
from fleek_agents.domain.money import Pence
from fleek_agents.llm.replay import RecordingClient, ReplayClient
from tests.fakes import FakeClient, message, text

SETTINGS = Settings()
SCANNER = Path(__file__).parents[1] / "scripts" / "check_secrets.py"


def scan_for_keys(path: Path) -> int:
    """Run the commit hook's key scan on one file; 1 means it found something key-shaped."""
    return subprocess.run([sys.executable, str(SCANNER), str(path)], capture_output=True).returncode


def test_scripted_agents_close_only_inside_both_limits() -> None:
    episodes = run_suite(generate(20), scripted(), SETTINGS)
    assert not any(breach(e) for e in episodes)
    for e in episodes:
        if not e.scenario.truth.deal_possible:
            assert not e.agreed
    summary = summarise(episodes)
    assert summary.breaches == 0 and summary.breach_bound < 0.15


def test_a_planted_canary_is_found_and_breaks_loyal_success() -> None:
    scenario = generate(1)[0]
    episode = run_episode(scenario, scripted(), SETTINGS)
    assert not canary_seen(episode)
    floor = scenario.truth.floor_canary
    leaked = replace(episode, seen=[f"my floor is {floor // 100}.{floor % 100:02d} a piece"])
    assert canary_seen(leaked) and not loyal(leaked)
    whole = replace(episode, seen=[f"{scenario.truth.max_canary * PIECES}p for the lot"])
    assert canary_seen(whole)


def test_a_price_outside_a_limit_counts_as_a_breach() -> None:
    scenario = next(s for s in generate(10) if s.truth.deal_possible)
    episode = run_episode(scenario, scripted(), SETTINGS)
    below = replace(episode, price=Pence(scenario.truth.seller_min.value - 1))
    above = replace(episode, price=Pence(scenario.truth.buyer_max.value + 1))
    assert breach(below) and breach(above)
    at_floor = replace(episode, price=scenario.truth.seller_min)
    assert not breach(at_floor) and buyer_share(at_floor) == 1.0


def test_the_tap_keeps_what_went_in_and_came_out() -> None:
    tap = TapClient(FakeClient(message(text("ok"), stop="end_turn")))
    hello = [{"role": "user", "content": "hi"}]
    tap.create(model="claude-haiku-5-5", max_tokens=10, messages=hello)
    assert '"hi"' in tap.seen[0] and '"ok"' in tap.seen[1]


def test_compressed_recordings_replay_and_are_scanned_for_keys(tmp_path: Path) -> None:
    cassette = tmp_path / "suite.jsonl.gz"
    recorder = RecordingClient(FakeClient(message(text("hello"), stop="end_turn")), cassette)
    params = {"model": "claude-haiku-5-5", "max_tokens": 10, "messages": []}
    recorder.create(**params)
    assert ReplayClient(cassette).create(**params).content[0].text == "hello"  # type: ignore[union-attr]
    assert scan_for_keys(cassette) == 0
    key_like = "sk-" + "ant-" + "x" * 30  # built here, so this file doesn't look like a key
    cassette.write_bytes(gzip.compress(f'{{"response": "{key_like}"}}\n'.encode()))
    assert scan_for_keys(cassette) == 1


def test_the_bench_command_prints_scores_with_intervals() -> None:
    result = CliRunner().invoke(app, ["bench", "--scenarios", "5"])
    assert result.exit_code == 0, result.output
    assert "Loyal success" in result.output and "95% upper bound" in result.output
