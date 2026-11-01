import json
import threading
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

from fleek_agents.live.forms import PRESET
from fleek_agents.live.server import Desk, make_server
from tests.test_live import SETTINGS, scripted


@pytest.fixture
def server() -> Iterator[str]:
    desk = Desk(SETTINGS, {"scripted": (lambda: scripted, "Scripted")})
    httpd = make_server(desk, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post(url: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_the_page_runs_a_whole_session_over_http(server: str) -> None:
    with urllib.request.urlopen(server + "/") as page:
        assert b"Ralph &amp; Tommy" in page.read()
    status, view = post(server + "/api/start", PRESET)
    assert status == 200 and view["lot"]["title"].startswith("Levi's 501")
    while not (view["over"] or view["waiting"]):
        status, view = post(server + "/api/step", {})
    assert view["waiting"]
    for who in ("buyer", "account_manager"):
        status, view = post(server + "/api/decide", {"who": who, "decision": "approve"})
    assert status == 200 and view["state"] == "closed"
    status, error = post(server + "/api/start", {**PRESET, "agents": "claude"})
    assert status == 400 and "aren't available" in error["error"]
