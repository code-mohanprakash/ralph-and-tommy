"""One agent turn: look-ups, then exactly one action.

The agent may call look-up tools (up to `max_lookups`), then must end the turn with exactly one
action tool. No action, two actions, or an input that doesn't fit its schema gets an error back
to correct, never a guess; after `max_corrections` the turn goes to a person. A refusal ends the
turn too. The conversation is only ever appended to: earlier turns are never edited.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from anthropic.types.beta import BetaMessage
from pydantic import BaseModel, ValidationError

from fleek_agents.harness.schemas import strict_schema
from fleek_agents.llm.budget import SpendCapReached
from fleek_agents.llm.client import LLMClient

NEED_ONE_ACTION = "End your turn with exactly one action tool call, and nothing else alongside it."


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    is_action: bool = False
    run: Callable[[BaseModel], str] | None = None  # look-ups only: returns text for the model

    def __post_init__(self) -> None:
        if self.is_action == (self.run is not None):
            raise ValueError(f"{self.name}: a look-up needs run(); an action must not have one")

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": strict_schema(self.input_model),
            "strict": True,
        }


class Outcome(StrEnum):
    ACTION = "action"
    NEEDS_HUMAN = "needs_human"  # too many corrections
    REFUSED = "refused"  # the model declined
    SPEND_CAP = "spend_cap"  # the next call could break a spend cap; a person takes over


@dataclass
class TurnResult:
    outcome: Outcome
    action: tuple[str, BaseModel] | None = None
    lookups: int = 0
    corrections: int = 0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    messages: list[dict[str, Any]] = field(default_factory=list)


def _error(block_id: str, why: str) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": block_id, "content": why, "is_error": True}


def take_turn(
    client: LLMClient,
    *,
    model: str,
    system: str,
    prompt: str,
    tools: Sequence[Tool],
    max_lookups: int = 6,
    max_corrections: int = 2,
    max_tokens: int = 4096,
    effort: str = "medium",
) -> TurnResult:
    by_name = {t.name: t for t in tools}
    result = TurnResult(outcome=Outcome.NEEDS_HUMAN)
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    result.messages = messages

    def correct(reply: list[dict[str, Any]] | str) -> bool:
        """Send a correction; False once there have been too many."""
        result.corrections += 1
        if result.corrections > max_corrections:
            return False
        messages.append({"role": "user", "content": reply})
        return True

    while True:
        try:
            response: BetaMessage = client.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=[t.definition() for t in tools],
                tool_choice={"type": "auto"},
                output_config={"effort": effort},
            )
        except SpendCapReached:
            result.outcome = Outcome.SPEND_CAP
            return result
        result.calls += 1
        result.input_tokens += response.usage.input_tokens
        result.output_tokens += response.usage.output_tokens
        if response.stop_reason == "refusal":
            result.outcome = Outcome.REFUSED
            return result
        messages.append(
            {"role": "assistant", "content": [b.model_dump() for b in response.content]}
        )

        uses = [b for b in response.content if b.type == "tool_use"]
        if not uses:
            if not correct(NEED_ONE_ACTION):
                return result
            continue

        actions = [u for u in uses if u.name in by_name and by_name[u.name].is_action]
        if actions and len(uses) > 1:  # an action must come alone
            if not correct([_error(u.id, NEED_ONE_ACTION) for u in uses]):
                return result
            continue

        replies: list[dict[str, Any]] = []
        failed = False
        for use in uses:
            tool = by_name.get(use.name)
            if tool is None:
                replies.append(_error(use.id, f"No tool called {use.name}."))
                failed = True
                continue
            try:
                parsed = tool.input_model.model_validate(use.input)
            except ValidationError as error:
                replies.append(
                    _error(use.id, f"Input didn't fit: {error.errors(include_url=False)}")
                )
                failed = True
                continue
            if tool.is_action:
                result.outcome, result.action = Outcome.ACTION, (tool.name, parsed)
                return result
            if result.lookups >= max_lookups:
                replies.append(
                    _error(use.id, f"Look-up limit ({max_lookups}) reached. Choose an action.")
                )
                continue
            result.lookups += 1
            assert tool.run is not None  # guaranteed by Tool.__post_init__; tells mypy
            replies.append(
                {"type": "tool_result", "tool_use_id": use.id, "content": tool.run(parsed)}
            )

        if failed:
            if not correct(replies):
                return result
        else:
            messages.append({"role": "user", "content": replies})
