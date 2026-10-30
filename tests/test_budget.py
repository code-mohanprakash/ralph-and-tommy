import pytest

from fleek_agents.config import Spending
from fleek_agents.harness.loop import Outcome, Tool, take_turn
from fleek_agents.llm.budget import BudgetedClient, Ledger, SpendCapReached, cost_microcents
from tests.fakes import FakeClient, call, message, text
from tests.test_tool_loop import NoInput

SPENDING = Spending()
WALK = Tool(name="walk_away", description="Leave.", input_model=NoInput, is_action=True)


def test_a_call_is_costed_from_its_tokens_at_the_model_s_price() -> None:
    # Haiku 5.5: 10 cents per million input tokens, 50 cents per million output tokens.
    # One token at X cents per million is X micro-cents.
    assert cost_microcents("claude-haiku-5-5", 1611, 354, SPENDING) == 1611 * 10 + 354 * 50
    assert cost_microcents("claude-sonnet-5-5", 1000, 1000, SPENDING) == 1000 * 200 + 1000 * 1000


def test_an_unknown_model_cant_be_budgeted() -> None:
    with pytest.raises(KeyError):
        cost_microcents("claude-mystery-9", 1, 1, SPENDING)


def test_spend_is_charged_to_the_negotiation_and_the_whole_run() -> None:
    run = Ledger(cap_microcents=10_000_000)
    negotiation = Ledger(cap_microcents=1_000_000, parent=run)
    client = BudgetedClient(
        FakeClient(message(call("walk_away", {}), tokens=1000)), negotiation, SPENDING
    )
    client.create(model="claude-haiku-5-5", max_tokens=100, messages=[])
    assert negotiation.spent == run.spent == 1000 * 10 + 1000 * 50


def test_a_call_that_could_break_the_cap_is_never_made() -> None:
    # 4,096 output tokens on Sonnet could cost 4,096 x 1,000 micro-cents: more than this cap.
    fake = FakeClient(message(call("walk_away", {})))
    tight = Ledger(cap_microcents=1_000_000)
    with pytest.raises(SpendCapReached):
        BudgetedClient(fake, tight, SPENDING).create(
            model="claude-sonnet-5-5", max_tokens=4096, messages=[]
        )
    assert fake.requests == []  # nothing was sent


def test_the_run_cap_applies_even_when_the_negotiation_has_room() -> None:
    run = Ledger(cap_microcents=100_000, spent=99_000)
    negotiation = Ledger(cap_microcents=10_000_000, parent=run)
    with pytest.raises(SpendCapReached):
        BudgetedClient(FakeClient(), negotiation, SPENDING).create(
            model="claude-haiku-5-5", max_tokens=100, messages=[]
        )


def test_a_turn_that_hits_the_cap_goes_to_a_person() -> None:
    # Worst case per call: 4,096 output tokens x 50 = 204,800 micro-cents. The first call
    # fits; it costs 60,000; then 60,000 + 204,800 is over the cap, so the second is never sent.
    ledger = Ledger(cap_microcents=250_000)
    responses = [
        message(text("thinking..."), stop="end_turn", tokens=1000),
        message(call("walk_away", {})),
    ]
    client = BudgetedClient(FakeClient(*responses), ledger, SPENDING)
    result = take_turn(
        client, model="claude-haiku-5-5", system="s", prompt="p", tools=[WALK], max_tokens=4096
    )
    assert result.outcome is Outcome.SPEND_CAP
    assert ledger.spent <= ledger.cap_microcents
