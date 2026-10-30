import pytest
from pydantic import BaseModel, ConfigDict

from fleek_agents.harness.loop import Outcome, Tool, ToolRefused, TurnResult, take_turn
from tests.fakes import FakeClient, call, message, text


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Offer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    price_pence: int


LOOKUP = Tool(
    name="get_lot", description="The lot.", input_model=NoInput, run=lambda _: "50 Levi's"
)
OFFER = Tool(name="send_offer", description="Offer a price.", input_model=Offer, is_action=True)
WALK = Tool(name="walk_away", description="Leave.", input_model=NoInput, is_action=True)
TOOLS = [LOOKUP, OFFER, WALK]


def turn(client: FakeClient, max_lookups: int = 6, max_corrections: int = 2) -> TurnResult:
    return take_turn(
        client,
        model="claude-haiku-5-5",
        system="You are Ralph.",
        prompt="Your turn.",
        tools=TOOLS,
        max_lookups=max_lookups,
        max_corrections=max_corrections,
    )


def test_look_ups_then_one_action() -> None:
    client = FakeClient(
        message(call("get_lot", {})),
        message(call("send_offer", {"price_pence": 1200})),
    )
    result = turn(client)
    assert result.outcome is Outcome.ACTION
    assert result.action == ("send_offer", Offer(price_pence=1200))
    assert result.lookups == 1 and result.corrections == 0
    second = client.requests[1]["messages"]
    assert second[-1]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "toolu_get_lot_1",
        "content": "50 Levi's",
    }


def test_no_action_gets_a_correction() -> None:
    client = FakeClient(
        message(text("I think £12 is fair."), stop="end_turn"), message(call("walk_away", {}))
    )
    result = turn(client)
    assert result.outcome is Outcome.ACTION and result.corrections == 1
    assert "exactly one action" in client.requests[1]["messages"][-1]["content"]


def test_two_actions_at_once_get_a_correction() -> None:
    client = FakeClient(
        message(call("send_offer", {"price_pence": 1}), call("walk_away", {}, n=2)),
        message(call("walk_away", {})),
    )
    result = turn(client)
    assert result.action is not None and result.action[0] == "walk_away"
    errors = client.requests[1]["messages"][-1]["content"]
    assert len(errors) == 2 and all(r["is_error"] for r in errors)  # every call gets an answer


def test_a_bad_input_is_returned_as_an_error_to_fix() -> None:
    client = FakeClient(
        message(call("send_offer", {"price_pence": "twelve pounds"})),
        message(call("send_offer", {"price_pence": 1200})),
    )
    result = turn(client)
    assert result.outcome is Outcome.ACTION and result.corrections == 1
    assert client.requests[1]["messages"][-1]["content"][0]["is_error"] is True


def test_too_many_corrections_hand_the_turn_to_a_person() -> None:
    client = FakeClient(*[message(text("hmm"), stop="end_turn")] * 3)
    result = turn(client, max_corrections=2)
    assert result.outcome is Outcome.NEEDS_HUMAN and result.action is None


def test_look_ups_past_the_limit_are_refused() -> None:
    lookups = [message(call("get_lot", {}, n=i)) for i in range(1, 4)]
    client = FakeClient(*lookups, message(call("walk_away", {})))
    result = turn(client, max_lookups=2)
    assert result.lookups == 2
    refused = client.requests[3]["messages"][-1]["content"][0]
    assert refused["is_error"] is True and "limit" in refused["content"]


def test_a_refusal_ends_the_turn() -> None:
    result = turn(FakeClient(message(text(""), stop="refusal")))
    assert result.outcome is Outcome.REFUSED


def test_history_is_only_ever_appended_to() -> None:
    client = FakeClient(
        message(call("get_lot", {})),
        message(text("hm"), stop="end_turn"),
        message(call("walk_away", {})),
    )
    turn(client)
    for earlier, later in zip(client.requests, client.requests[1:], strict=False):
        assert later["messages"][: len(earlier["messages"])] == earlier["messages"]


def test_tokens_are_added_up_across_calls() -> None:
    client = FakeClient(
        message(call("get_lot", {}), tokens=7), message(call("walk_away", {}), tokens=5)
    )
    result = turn(client)
    assert (result.input_tokens, result.output_tokens, result.calls) == (12, 12, 2)


def test_a_look_up_must_have_something_to_run_and_an_action_must_not() -> None:
    with pytest.raises(ValueError):
        Tool(name="get_lot", description="x", input_model=NoInput)
    with pytest.raises(ValueError):
        Tool(
            name="walk_away", description="x", input_model=NoInput, is_action=True, run=lambda _: ""
        )


def test_a_correction_gives_plain_reasons_not_a_dump_of_the_input() -> None:
    client = FakeClient(
        message(call("send_offer", {"price_pence": "twelve pounds"})),
        message(call("send_offer", {"price_pence": 1200})),
    )
    turn(client)
    error = client.requests[1]["messages"][-1]["content"][0]["content"]
    assert "price_pence" in error and "twelve pounds" not in error


def test_a_refused_look_up_is_answered_as_an_error_without_counting_as_a_mistake() -> None:
    def once_only(_: BaseModel) -> str:
        raise ToolRefused("Only once per round.")

    limited = Tool(name="check_price", description="Band.", input_model=NoInput, run=once_only)
    client = FakeClient(message(call("check_price", {})), message(call("walk_away", {})))
    result = take_turn(
        client, model="claude-haiku-5-5", system="s", prompt="p", tools=[limited, WALK]
    )
    refused = client.requests[1]["messages"][-1]["content"][0]
    assert refused["is_error"] is True and "once per round" in refused["content"]
    assert result.corrections == 0 and result.outcome is Outcome.ACTION
