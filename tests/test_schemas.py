import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Terms
from fleek_agents.harness.loop import Outcome, Tool, take_turn
from fleek_agents.harness.schemas import UNSUPPORTED, strict_schema
from fleek_agents.llm.client import LiveClient
from fleek_agents.llm.env import load_env_file
from tests.fakes import FakeClient, call, message


def walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def test_a_strict_schema_keeps_the_shape_and_drops_what_strict_mode_refuses() -> None:
    schema = strict_schema(Terms)
    nodes = list(walk(schema))
    assert not any(UNSUPPORTED & node.keys() for node in nodes)
    objects = [n for n in nodes if n.get("type") == "object"]
    assert objects and all(n.get("additionalProperties") is False for n in objects)
    assert set(schema["required"]) == {"base_price", "bundles", "prepaid", "ship_by"}
    assert schema["properties"]["ship_by"]["format"] == "date"


def test_dropped_limits_are_still_checked_on_our_side() -> None:
    # The API no longer stops a 0-bundle offer; Pydantic does, and the model gets a correction.
    terms = {"base_price": 1200, "bundles": 0, "prepaid": False, "ship_by": "2026-11-20"}
    good = {**terms, "bundles": 1}
    client = FakeClient(message(call("send_offer", terms)), message(call("send_offer", good)))
    tool = Tool(name="send_offer", description="Offer.", input_model=Terms, is_action=True)
    result = take_turn(client, model="claude-haiku-5-5", system="s", prompt="p", tools=[tool])
    assert result.corrections == 1 and result.outcome is Outcome.ACTION


def test_every_tool_is_sent_as_strict() -> None:
    tool = Tool(name="send_offer", description="Offer.", input_model=Terms, is_action=True)
    assert tool.definition()["strict"] is True


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@pytest.mark.skipif(
    os.environ.get("FLEEK_LIVE") != "1", reason="calls the real API; set FLEEK_LIVE=1"
)
@pytest.mark.parametrize("model", ["claude-haiku-5-5", "claude-sonnet-5-5"])
def test_a_live_turn_with_strict_tools(model: str) -> None:
    load_env_file(Path(__file__).parents[1] / ".env")
    lookup = Tool(
        name="get_lot",
        description="Details of the lot you are buying.",
        input_model=NoInput,
        run=lambda _: (
            "50 Levi's 501 jeans, grade A. Listed at 1350 pence per piece plus 300 shipping."
        ),
    )
    offer = Tool(
        name="send_offer",
        description="Send your offer. Ends your turn.",
        input_model=Terms,
        is_action=True,
    )
    result = take_turn(
        LiveClient(),
        model=model,
        system="You buy secondhand clothing in bulk. Prices are whole pence per piece.",
        prompt="Look up the lot, then make an opening offer for 1 bundle, shipping by 2026-11-20.",
        tools=[lookup, offer],
        effort="low",
    )
    assert result.outcome is Outcome.ACTION, result.outcome
    assert result.action is not None and result.action[0] == "send_offer"
    terms = result.action[1]
    assert isinstance(terms, Terms) and Pence(0) < terms.base_price
    tokens = f"{result.input_tokens} in, {result.output_tokens} out"
    print(f"\n{model}: offered {terms.base_price}, {result.calls} calls, {tokens}")
