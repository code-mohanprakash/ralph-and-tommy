"""The live demo's web server, on this computer only (127.0.0.1).

GET  /              the page: onboarding, then the two screens
GET  /static/NAME   the page's own files
GET  /api/preset    a ready-made onboarding (the one with a Claude recording)
GET  /api/state     both screens, as JSON
POST /api/start     start a session from the onboarding form
POST /api/step      one turn
POST /api/control   pause, resume, stop or hand over, by the buyer or the seller
POST /api/decide    approve or reject, by whoever is asked

Python's own http.server, like the Deal Room: nothing to install, nothing from the internet.
"""

import json
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from fleek_agents.config import Settings
from fleek_agents.domain.state import IllegalMove
from fleek_agents.live.forms import BUYERS, PRESET, FormError, Setup
from fleek_agents.live.session import AgentPair, LiveSession
from fleek_agents.llm.replay import CassetteMiss
from fleek_agents.orchestrator.opening import NoTriesLeft

STATIC = Path(__file__).parent / "static"
TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}
MAX_BODY = 20_000


class BadRequest(ValueError):
    pass


class Desk:
    """The one session the page drives. One person at a time, so one lock."""

    def __init__(
        self,
        settings: Settings,
        pairs: dict[str, tuple[Callable[[], AgentPair], str]],
    ) -> None:
        self.settings, self.pairs = settings, pairs
        self.live: LiveSession | None = None
        self._lock = threading.Lock()

    def options(self) -> dict[str, Any]:
        return {
            "preset": PRESET,
            "buyers": BUYERS,
            "agents": [{"key": k, "label": label} for k, (_, label) in self.pairs.items()],
        }

    def start(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            setup = Setup.model_validate(body)
        except ValidationError as error:
            first = error.errors()[0]
            where = " → ".join(str(p) for p in first["loc"])
            raise BadRequest(f"{where}: {first['msg']}") from None
        if setup.agents not in self.pairs:
            raise BadRequest(f"These agents aren't available here: {setup.agents}")
        make, label = self.pairs[setup.agents]
        with self._lock:
            try:
                self.live = LiveSession(setup, self.settings, make(), label)
            except FormError as error:
                raise BadRequest(str(error)) from None
            return self.live.view()

    def _session(self) -> LiveSession:
        if self.live is None:
            raise BadRequest("Start a session first.")
        return self.live

    def state(self) -> dict[str, Any]:
        with self._lock:
            return self._session().view() if self.live else {"state": "onboarding"}

    def step(self, _body: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            live = self._session()
            try:
                live.step()
            except CassetteMiss:
                raise BadRequest(
                    "The recording doesn't cover these numbers. Use the scripted agents, or "
                    "restart with --live to ask Claude now."
                ) from None
            return live.view()

    def control(self, body: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            live = self._session()
            try:
                live.control(str(body.get("action")), str(body.get("side")))
            except (FormError, IllegalMove) as error:
                raise BadRequest(str(error)) from None
            return live.view()

    def decide(self, body: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            live = self._session()
            try:
                live.decide(str(body.get("who")), str(body.get("decision")))
            except (FormError, IllegalMove, NoTriesLeft) as error:
                raise BadRequest(str(error)) from None
            return live.view()


def make_handler(desk: Desk) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

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
            if path == "/api/options":
                self._json(HTTPStatus.OK, desk.options())
                return
            if path == "/api/state":
                self._json(HTTPStatus.OK, desk.state())
                return
            name = "live.html" if path == "/" else path.removeprefix("/static/")
            file = STATIC / Path(name).name
            if (path == "/" or path.startswith("/static/")) and file.is_file():
                self._send(HTTPStatus.OK, file.read_bytes(), TYPES.get(file.suffix, "text/plain"))
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

        def do_POST(self) -> None:
            actions = {
                "/api/start": desk.start,
                "/api/step": desk.step,
                "/api/control": desk.control,
                "/api/decide": desk.decide,
            }
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


def make_server(desk: Desk, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(desk))
