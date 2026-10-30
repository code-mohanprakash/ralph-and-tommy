"""Record real model calls once, then replay them in tests: free, offline, the same every run.

A cassette is a JSON Lines file: one line per call, holding a fingerprint of the request and the
response exactly as the API returned it. Replaying looks a request up by its fingerprint, so if
a prompt, tool or setting changes, the old recording no longer matches and the test says so,
rather than quietly replaying an answer to a different question.

Requests never contain the API key (the SDK sends it as a header), and the key scan runs on
cassettes like every other committed file.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from anthropic.types.beta import BetaMessage

from fleek_agents.llm.client import LiveClient, LLMClient


class CassetteMiss(Exception):
    """No recording for this request. Re-record with FLEEK_LIVE=1 FLEEK_RECORD=1."""


def fingerprint(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class RecordingClient:
    """Passes calls to a real client and writes each request and response to the cassette."""

    def __init__(self, inner: LLMClient, cassette: Path) -> None:
        self._inner, self._cassette = inner, cassette
        cassette.parent.mkdir(parents=True, exist_ok=True)
        cassette.write_text("")  # a recording replaces the old one

    def create(self, **params: Any) -> BetaMessage:
        response = self._inner.create(**params)
        line = {
            "request": fingerprint(params),
            "model": params["model"],
            "response": response.model_dump(mode="json"),
        }
        with self._cassette.open("a", encoding="utf-8") as file:
            file.write(json.dumps(line, sort_keys=True) + "\n")
        return response


class ReplayClient:
    """Answers from the cassette. Never touches the network."""

    def __init__(self, cassette: Path) -> None:
        self._answers: dict[str, list[dict[str, Any]]] = {}
        for raw in cassette.read_text(encoding="utf-8").splitlines():
            line = json.loads(raw)
            self._answers.setdefault(line["request"], []).append(line["response"])

    def create(self, **params: Any) -> BetaMessage:
        answers = self._answers.get(fingerprint(params))
        if not answers:
            raise CassetteMiss(f"No recording for this {params['model']} request")
        return BetaMessage.model_validate(answers.pop(0))


def cassette_client(cassette: Path) -> LLMClient:
    """Record live when FLEEK_RECORD=1 (needs the key); otherwise replay."""
    if os.environ.get("FLEEK_RECORD") == "1":
        return RecordingClient(LiveClient(), cassette)
    return ReplayClient(cassette)
