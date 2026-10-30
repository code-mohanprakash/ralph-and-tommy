"""A pretend Claude for tests: plays back a list of responses and records every request."""

from typing import Any

from anthropic.types.beta import BetaMessage


def message(*blocks: dict[str, Any], stop: str = "tool_use", tokens: int = 10) -> BetaMessage:
    return BetaMessage.model_validate(
        {
            "id": "msg_fake",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-5-5",
            "content": list(blocks),
            "stop_reason": stop,
            "stop_sequence": None,
            "usage": {"input_tokens": tokens, "output_tokens": tokens},
        }
    )


def call(name: str, tool_input: dict[str, Any], n: int = 1) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"toolu_{name}_{n}", "name": name, "input": tool_input}


def text(words: str) -> dict[str, Any]:
    return {"type": "text", "text": words}


class FakeClient:
    def __init__(self, *responses: BetaMessage) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def create(self, **params: Any) -> BetaMessage:
        # Copy the messages list: the loop keeps appending to its own.
        self.requests.append({**params, "messages": list(params["messages"])})
        return self._responses.pop(0)
