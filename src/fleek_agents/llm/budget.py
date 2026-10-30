"""Spend caps: no loop can run up a bill.

Every call is costed from the tokens the API reports, at the model's list price. Costs are kept
in micro-cents (millionths of a US cent): one token at X cents per million tokens costs exactly X
micro-cents, so the maths stays in whole numbers.

Before each call the worst case is checked: if the call's maximum output alone could break a cap
(the negotiation's or the whole run's), it isn't made. Input tokens aren't known in advance, so a
call can still go over by its input cost; a cap is a ceiling with that small margin, not exact.
Prompt caching changes input prices: writing to the cache costs more than plain input (up to 2x,
for one-hour caching) and reading from it costs less. Writes are charged at 2x and reads at 1x,
so the ledger can overstate the cost but never understate it.
"""

from dataclasses import dataclass
from typing import Any

from anthropic.types.beta import BetaMessage

from fleek_agents.config import Spending
from fleek_agents.llm.client import LLMClient

CACHE_WRITE_MULTIPLIER = 2  # the highest cache-write price: one-hour caching, 2x input


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
        writes = (usage.cache_creation_input_tokens or 0) * CACHE_WRITE_MULTIPLIER
        reads = usage.cache_read_input_tokens or 0
        input_equivalent = usage.input_tokens + writes + reads
        self._ledger.charge(
            cost_microcents(model, input_equivalent, usage.output_tokens, self._spending)
        )
        return response
