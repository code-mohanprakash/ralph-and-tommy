from pathlib import Path

import pytest

from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Terms
from fleek_agents.harness.loop import Outcome, Tool, TurnResult, take_turn
from fleek_agents.llm.client import LLMClient
from fleek_agents.llm.env import load_env_file
from fleek_agents.llm.replay import CassetteMiss, RecordingClient, ReplayClient, cassette_client
from tests.fakes import FakeClient, call, message
from tests.test_tool_loop import NoInput

CASSETTES = Path(__file__).parent / "cassettes"
LOOKUP = Tool(
    name="get_lot",
    description="Details of the lot you are buying.",
    input_model=NoInput,
    run=lambda _: "50 Levi's 501 jeans, grade A. Listed at 1350 pence per piece plus 300 shipping.",
)
OFFER = Tool(
    name="send_offer",
    description="Send your offer. Ends your turn.",
    input_model=Terms,
    is_action=True,
)


def opening_offer(client: LLMClient) -> TurnResult:
    return take_turn(
        client,
        model="claude-haiku-5-5",
        system="You buy secondhand clothing in bulk. Prices are whole pence per piece.",
        prompt="Look up the lot, then make an opening offer for 1 bundle, shipping by 2026-11-20.",
        tools=[LOOKUP, OFFER],
        effort="low",
    )


def test_a_recorded_live_turn_replays_offline() -> None:
    load_env_file(Path(__file__).parents[1] / ".env")  # only used when recording
    result = opening_offer(cassette_client(CASSETTES / "haiku_opening_offer.jsonl"))
    assert result.outcome is Outcome.ACTION and result.action is not None
    terms = result.action[1]
    assert isinstance(terms, Terms) and Pence(0) < terms.base_price


def test_replaying_twice_gives_the_same_answer() -> None:
    cassette = CASSETTES / "haiku_opening_offer.jsonl"
    first = opening_offer(ReplayClient(cassette))
    again = opening_offer(ReplayClient(cassette))
    assert first.action == again.action


def test_a_changed_request_doesn_t_match_an_old_recording(tmp_path: Path) -> None:
    cassette = tmp_path / "c.jsonl"
    recorder = RecordingClient(FakeClient(message(call("walk_away", {}))), cassette)
    recorder.create(
        model="claude-haiku-5-5", max_tokens=10, messages=[{"role": "user", "content": "a"}]
    )
    replay = ReplayClient(cassette)
    with pytest.raises(CassetteMiss):
        replay.create(
            model="claude-haiku-5-5", max_tokens=10, messages=[{"role": "user", "content": "b"}]
        )
    assert replay.create(
        model="claude-haiku-5-5", max_tokens=10, messages=[{"role": "user", "content": "a"}]
    )
