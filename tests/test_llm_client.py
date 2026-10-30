import os
from pathlib import Path
from typing import Any

import pytest
from anthropic.types.beta import BetaMessage

from fleek_agents.config import ModelRouting, load_settings
from fleek_agents.domain.money import Pence
from fleek_agents.llm.client import LiveClient
from fleek_agents.llm.env import load_env_file
from fleek_agents.llm.routing import model_for

ROUTING = ModelRouting()
EMPTY = BetaMessage.model_validate(
    {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
)


@pytest.mark.parametrize(
    ("value", "model"),
    [
        (99_999, "claude-haiku-5-5"),
        (100_000, "claude-sonnet-5-5"),
        (2_500_000, "claude-sonnet-5-5"),
    ],
)
def test_big_deals_get_sonnet_and_small_ones_haiku(value: int, model: str) -> None:
    assert model_for(Pence(value), ROUTING) == model


def test_the_routing_comes_from_market_toml() -> None:
    settings = load_settings(Path(__file__).parents[1] / "market.toml")
    assert settings.models.big_deal_pence == 100_000  # £1,000
    assert settings.models.digest_model == "claude-opus-5-5"


class FakeSDK:
    """Stands in for anthropic.Anthropic and records what would have been sent."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.beta = self
        self.messages = self

    def create(self, **params: Any) -> BetaMessage:
        self.sent.append(params)
        return EMPTY


@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-opus-5-5"])
def test_sonnet_and_opus_ask_for_the_refusal_fallback(model: str) -> None:
    sdk = FakeSDK()
    LiveClient(sdk).create(model=model, max_tokens=10, messages=[])  # type: ignore[arg-type]
    assert sdk.sent[0]["fallbacks"] == "default"
    assert sdk.sent[0]["betas"] == ["server-side-fallback-2026-07-01"]


def test_haiku_has_no_fallback_to_ask_for() -> None:
    sdk = FakeSDK()
    LiveClient(sdk).create(model="claude-haiku-5-5", max_tokens=10, messages=[])  # type: ignore[arg-type]
    assert "fallbacks" not in sdk.sent[0]


def test_the_env_file_sets_missing_values_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text("# a comment\nFLEEK_TEST_A=from-file\nFLEEK_TEST_B=from-file\n\nnot a setting\n")
    monkeypatch.delenv("FLEEK_TEST_A", raising=False)
    monkeypatch.setenv("FLEEK_TEST_B", "already-set")
    loaded = load_env_file(env)
    assert os.environ["FLEEK_TEST_A"] == "from-file"
    assert os.environ["FLEEK_TEST_B"] == "already-set"  # the environment wins
    assert loaded == ["FLEEK_TEST_A"]  # names only, never values


def test_a_missing_env_file_is_fine(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "nope.env") == []


@pytest.mark.skipif(
    os.environ.get("FLEEK_LIVE") != "1", reason="calls the real API; set FLEEK_LIVE=1"
)
def test_one_live_call_to_haiku() -> None:
    load_env_file(Path(__file__).parents[1] / ".env")
    response = LiveClient().create(
        model="claude-haiku-5-5",
        max_tokens=1024,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": "Reply with just the word: ready"}],
    )
    assert response.stop_reason == "end_turn"
    text = "".join(b.text for b in response.content if b.type == "text")
    assert "ready" in text.lower()
