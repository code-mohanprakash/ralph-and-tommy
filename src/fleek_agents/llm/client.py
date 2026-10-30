"""Talking to Claude, behind one small interface.

Everything that needs the model takes an LLMClient. The live one calls the Anthropic API; tests,
record-and-replay and scripted runs supply their own, so nothing else in the code knows or cares
which it is, and CI never needs a key.
"""

from typing import Any, Protocol

import anthropic
from anthropic.types.beta import BetaMessage

# If one of these declines on a safety rule, the API re-runs the request on a suitable model
# within the same call ("default" routes by refusal category). Claude Haiku 5.5 has no
# server-side fallback; its refusals go to a person instead.
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMClient(Protocol):
    def create(self, **params: Any) -> BetaMessage: ...


class LiveClient:
    """The real API. Reads the key from the environment (see llm/env.py); never takes it here."""

    def __init__(self, sdk: anthropic.Anthropic | None = None) -> None:
        self._sdk = sdk or anthropic.Anthropic()

    def create(self, **params: Any) -> BetaMessage:
        if params["model"] in FALLBACK_MODELS:
            params = {**params, "betas": [FALLBACK_BETA], "fallbacks": "default"}
        response = self._sdk.beta.messages.create(**params)
        if not isinstance(response, BetaMessage):  # a stream; nothing here asks for one
            raise TypeError("Expected a complete message, not a stream")
        return response
