"""Spend caps: no loop can run up a bill.

Every call is costed from the tokens the API reports, at the model's list price. Costs are kept
in micro-cents (millionths of a US cent): one token at X cents per million tokens costs exactly X
micro-cents, so the maths stays in whole numbers.

Before each call the worst case is checked: if the call's maximum output alone could break a cap
(the negotiation's or the whole run's), it isn't made. Input tokens aren't known in advance, so a
call can still go over by its input cost; a cap is a ceiling with that small margin, not exact.
Cached input tokens are charged at the full input price, which can only overstate the cost.
"""

from dataclasses import dataclass
from typing import Any

from anthropic.types.beta import BetaMessage

from fleek_agents.config import Spending
from fleek_agents.llm.client import LLMClient


class SpendCapReached(Exception):
    """The next call could cost more than the money left under a cap."""


@dataclass
class Ledger:
    cap_microcents: int
    spent: int = 0
    parent: "Ledger | None" = None  # e.g. a negotiation's ledger, inside the run's

    def room(self) -> int:
        left = self.cap_microcents - self.spent
        return min(left, self.parent.room()) if self.parent else left

    def charge(self, microcents: int) -> None:
        self.spent += microcents
        if self.parent:
            self.parent.charge(microcents)


def cost_microcents(model: str, input_tokens: int, output_tokens: int, spending: Spending) -> int:
    price = spending.prices[model]  # KeyError for a model we have no price for: refuse to guess
    return input_tokens * price.input_cents_per_mtok + output_tokens * price.output_cents_per_mtok


class BudgetedClient:
    """Wraps any LLMClient and charges every call to a ledger."""

    def __init__(self, inner: LLMClient, ledger: Ledger, spending: Spending) -> None:
        self._inner, self._ledger, self._spending = inner, ledger, spending

    def create(self, **params: Any) -> BetaMessage:
        model, max_tokens = params["model"], params["max_tokens"]
        worst_output = cost_microcents(model, 0, max_tokens, self._spending)
        if worst_output > self._ledger.room():
            raise SpendCapReached(f"{model} could cost more than is left under the cap")
        response = self._inner.create(**params)
        usage = response.usage
        cached = (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0)
        self._ledger.charge(
            cost_microcents(model, usage.input_tokens + cached, usage.output_tokens, self._spending)
        )
        return response
