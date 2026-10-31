"""A small web server for the Deal Room, on this computer only (127.0.0.1).

GET  /              the page
GET  /static/NAME   the page's own files (scripts, styles), from this package
GET  /api/scenarios the ready-made scenarios, for the buttons
POST /api/run       run one negotiation with the limits given; answers with the story as JSON
POST /api/decide    approve or reject the last run's deal, as the account manager

Python's own http.server: no web framework to install, and nothing loads from the internet, so
the demo works without wifi.
"""

import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from fleek_agents.agents.base import Agent
from fleek_agents.config import Settings
from fleek_agents.domain.money import Pence
from fleek_agents.domain.state import NegotiationState
from fleek_agents.orchestrator.approval import approve, reject
from fleek_agents.room.play import RoomRun, run_room
from fleek_agents.room.scenario import SCENARIOS, RoomInput
from fleek_agents.room.story import story

STATIC = Path(__file__).parent / "static"
TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
}
MAX_BODY = 10_000

AgentPair = Callable[[], tuple[Agent, Agent]]  # fresh Ralph and Tommy for each run


class BadRequest(ValueError):
    pass


def read_input(body: dict[str, Any]) -> RoomInput:
    try:
        return RoomInput(
            buyer_max=Pence(int(body["buyer_max"])),
            seller_floor=Pence(int(body["seller_floor"])),
            pairs=int(body.get("pairs", 200)),
            regular_buyer=bool(body.get("regular_buyer", False)),
            tommy_breaks_a_rule=bool(body.get("tommy_breaks_a_rule", False)),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise BadRequest(f"Can't run with that: {error}") from None


def scenarios() -> list[dict[str, Any]]:
    return [
        {
            "key": x.key,
            "label": x.label,
            "shows": x.shows,
            "input": {
                "buyer_max": x.room.buyer_max.value,
                "seller_floor": x.room.seller_floor.value,
                "pairs": x.room.pairs,
                "regular_buyer": x.room.regular_buyer,
                "tommy_breaks_a_rule": x.room.tommy_breaks_a_rule,
            },
        }
        for x in SCENARIOS
    ]


class Room:
    """What the server keeps between requests: the settings, the agents, and the last run."""

    def __init__(self, settings: Settings, agents: AgentPair) -> None:
        self.settings, self.agents = settings, agents
        self.last: RoomRun | None = None
        self._lock = threading.Lock()  # one run at a time; the page is for one person

    def run(self, body: dict[str, Any]) -> dict[str, Any]:
        room = read_input(body)
        with self._lock:
            ralph, tommy = self.agents()
            self.last = run_room(room, ralph=ralph, tommy=tommy, settings=self.settings)
            return story(self.last)

    def decide(self, body: dict[str, Any]) -> dict[str, Any]:
        decision = body.get("decision")
        with self._lock:
            run = self.last
            if run is None or run.negotiation_id is None:
                raise BadRequest("No deal to decide on yet.")
            nid, log = run.negotiation_id, run.log
            if log.state(nid) is not NegotiationState.PENDING_APPROVAL:
                raise BadRequest("This deal isn't waiting for a person.")
            if decision == "approve":
                approve(log, nid, at=datetime.now(UTC))
                say = "Approved by the account manager. The deal is final, and the truck leaves."
            elif decision == "reject":
                reject(log, nid, at=datetime.now(UTC))
                say = "Rejected by the account manager. The jeans go back on sale."
            else:
                raise BadRequest("Decision must be approve or reject.")
            return {"state": str(log.state(nid)), "say": say}


def make_handler(room: Room) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass  # keep the terminal quiet during a demo

        def _send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data: dict[str, Any]) -> None:
            self._send(status, json.dumps(data).encode(), "application/json")

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path == "/api/scenarios":
                self._json(HTTPStatus.OK, {"scenarios": scenarios()})
                return
            name = "index.html" if path == "/" else path.removeprefix("/static/")
            file = STATIC / Path(name).name  # .name: no way out of the folder
            if (path == "/" or path.startswith("/static/")) and file.is_file():
                self._send(HTTPStatus.OK, file.read_bytes(), TYPES.get(file.suffix, "text/plain"))
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

        def do_POST(self) -> None:
            actions = {"/api/run": room.run, "/api/decide": room.decide}
            action = actions.get(self.path)
            if action is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Too big"})
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise BadRequest("Send a JSON object.")
                self._json(HTTPStatus.OK, action(body))
            except (BadRequest, json.JSONDecodeError) as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    return Handler


def make_server(room: Room, port: int) -> ThreadingHTTPServer:
    """Listen on this computer only. Port 0 picks a free one (the tests use that)."""
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(room))
