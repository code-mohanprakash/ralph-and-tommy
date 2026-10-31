"""The Deal Room: a real negotiation, told as steps, served on this computer only."""

import json
import re
import socket
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from fleek_agents.agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.cli import app
from fleek_agents.config import Settings, load_settings
from fleek_agents.domain.money import Pence
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.run import run_negotiation
from fleek_agents.room.play import START, run_room
from fleek_agents.humans.digest import call_list
from fleek_agents.room.scenario import (
    DELHI,
    KARACHI,
    LAHORE,
    SCENARIOS,
    RoomInput,
    room_market,
    room_secrets,
)
from fleek_agents.room.server import BadRequest, Room, make_server, read_input
from fleek_agents.room.story import story
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog
from fleek_agents.store.market import load_market

ROOT = Path(__file__).parent.parent
DEFAULT = RoomInput(buyer_max=Pence(1550), seller_floor=Pence(935))


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings(ROOT / "market.toml")


def play(room: RoomInput, settings: Settings) -> dict[str, Any]:
    return story(run_room(room, ralph=ScriptedRalph(), tommy=ScriptedTommy(), settings=settings))


def test_the_default_room_tells_the_whole_deal_in_order(settings: Settings) -> None:
    s = play(DEFAULT, settings)
    kinds = [step["kind"] for step in s["steps"]]
    assert kinds == [
        "tell",
        "secret",
        "list",
        "secret",
        "filter",
        "check",
        "check",
        "matched",
        "card",
        "card",
        "card",
        "card",
        "card",
        "accept",
        "money",
        "waiting",
    ]
    assert [step["price"] for step in s["steps"] if step["kind"] == "card"] == [
        1120,
        1400,
        1120,
        1305,
        1210,
    ]
    assert s["outcome"]["state"] == "pending_approval"
    assert s["outcome"]["price"] == 1210
    assert s["outcome"]["buyer_pays"] == 304000  # (£12.10 + £3.00) x 200 + £20 fee
    assert s["outcome"]["why_waiting"] == "£1,500 or more"


def test_matching_drops_lahore_by_the_filters_and_delhi_by_the_vault(
    settings: Settings,
) -> None:
    sellers = {x["id"]: x for x in play(DEFAULT, settings)["sellers"]}
    assert sellers[LAHORE]["passed_filters"] is False  # grade C; the shop wants A
    assert sellers[LAHORE]["possible"] is None  # the vault was never asked
    assert sellers[DELHI]["possible"] is False  # its floor is above its own list price
    assert sellers[KARACHI]["possible"] is True and sellers[KARACHI]["chosen"] is True


@pytest.mark.parametrize(
    ("buyer_max", "seller_floor", "pairs"),
    [(1550, 935, 200), (1340, 1015, 50), (1990, 655, 300), (1000, 1100, 200), (1290, 1065, 150)],
)
def test_the_steps_never_hold_a_secret_limit(
    settings: Settings, buyer_max: int, seller_floor: int, pairs: int
) -> None:
    s = play(RoomInput(Pence(buyer_max), Pence(seller_floor), pairs), settings)
    secrets = [Pence(buyer_max), Pence(seller_floor)]
    public = [st["price"] for st in s["steps"]] + [x["list_price"] for x in s["sellers"]]
    for value in (s["audience"]["buyer_highest_card"], s["audience"]["seller_lowest_card"]):
        if value is not None and value not in public:
            secrets.append(Pence(value))  # an edge is public only if a card or a list price is
    text = json.dumps(s["steps"], ensure_ascii=False)  # keep "£" readable, not \\u00a3
    for secret in secrets:
        pounds = f"{secret.value // 100}.{secret.value % 100:02d}"  # 15.50, with or without £
        assert pounds not in text and f"={secret.value}" not in text, f"{secret} is in a step"
    assert s["audience"]["buyer_max"] == buyer_max  # the limits are in the audience block only
    assert s["audience"]["seller_floor"] == seller_floor


def test_a_regular_shop_buying_one_bundle_is_approved_by_the_rule(settings: Settings) -> None:
    s = play(RoomInput(Pence(1550), Pence(935), pairs=50, regular_buyer=True), settings)
    assert s["outcome"]["state"] == "closed"
    assert s["outcome"]["buyer_pays"] < 150000
    assert s["steps"][-1]["kind"] == "approved"


def test_a_new_shop_waits_for_a_person_even_for_one_bundle(settings: Settings) -> None:
    s = play(RoomInput(Pence(1550), Pence(935), pairs=50), settings)
    assert s["outcome"]["state"] == "pending_approval"
    assert s["outcome"]["why_waiting"] == "one of the buyer's first 3 deals"


def test_a_max_below_the_floor_never_opens_a_negotiation(settings: Settings) -> None:
    s = play(RoomInput(Pence(1000), Pence(1100)), settings)
    assert s["negotiation_id"] is None
    assert s["steps"][-1]["kind"] == "no_match"
    assert not [st for st in s["steps"] if st["kind"] == "card"]
    assert s["audience"]["buyer_highest_card"] is None


def test_every_deal_lands_between_the_two_edges(settings: Settings) -> None:
    for buyer_max, floor in [(1550, 935), (1700, 800), (1450, 1000), (1600, 1050)]:
        s = play(RoomInput(Pence(buyer_max), Pence(floor)), settings)
        if "price" in s["outcome"]:
            a = s["audience"]
            assert a["seller_lowest_card"] <= s["outcome"]["price"] <= a["buyer_highest_card"]


def test_watching_the_agents_changes_nothing_they_do(settings: Settings) -> None:
    """The same deal, run with plain run_negotiation, records exactly the same moves."""
    room = DEFAULT
    run = run_room(room, ralph=ScriptedRalph(), tommy=ScriptedTommy(), settings=settings)
    assert run.lot is not None and run.negotiation_id is not None
    market = room_market(room.pairs)
    secrets = room_secrets(market, room)
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        load_market(session, market)
        log, clock = EventLog(session), FakeClock(START)
        nid = open_negotiation(
            log, buyer_id="buyer-9001", lot_id=run.lot.id, clock=clock, rules=settings.negotiation
        )
        run_negotiation(
            log,
            nid,
            lot=run.lot,
            seller=market.sellers[1],
            want=market.wants[0],
            bundles=run.bundles,
            buyer_limit=secrets.buyers["buyer-9001"],
            seller_limit=secrets.lots[run.lot.id],
            ralph=ScriptedRalph(),
            tommy=ScriptedTommy(),
            clock=clock,
            settings=settings,
        )
        plain = [(e.move, e.by, e.card.base_price if e.card else None) for e in log.read(nid)]
    watched = [
        (e.move, e.by, e.card.base_price if e.card else None)
        for e in run.log.read(run.negotiation_id)
    ]
    assert watched[: len(plain)] == plain  # the room adds only the approval step after


SCENARIO = {x.key: x for x in SCENARIOS}


@pytest.mark.parametrize(
    ("key", "state", "last_step"),
    [
        ("deal", "pending_approval", "waiting"),
        ("small", "closed", "approved"),
        ("broken", "needs_human", "blocked"),
        ("near_miss", "walked_away", "walk"),
        ("no_match", "no_match", "no_match"),
    ],
)
def test_each_scenario_ends_the_way_its_button_says(
    settings: Settings, key: str, state: str, last_step: str
) -> None:
    s = play(SCENARIO[key].room, settings)
    assert s["outcome"]["state"] == state
    assert s["steps"][-1]["kind"] == last_step


def test_the_near_miss_had_a_price_and_lands_on_the_call_list(settings: Settings) -> None:
    run = run_room(
        SCENARIO["near_miss"].room, ralph=ScriptedRalph(), tommy=ScriptedTommy(), settings=settings
    )
    lowest, highest = run.limits.seller_lowest, run.limits.buyer_highest
    assert lowest is not None and highest is not None and lowest <= highest  # a deal was possible
    items = call_list(run.log, {x.id: x for x in run.market.lots}, settings.digest)
    assert [i.negotiation_id for i in items] == [run.negotiation_id]
    assert items[0].gap_pct <= settings.digest.near_miss_gap_pct


def test_the_broken_tommy_changes_only_his_second_counter(settings: Settings) -> None:
    def moves(s: dict[str, Any]) -> list[tuple[str, int]]:
        return [(st["kind"], st["price"]) for st in s["steps"] if st["kind"] in ("card", "blocked")]

    honest, broken = play(DEFAULT, settings), play(SCENARIO["broken"].room, settings)
    assert moves(broken)[:3] == moves(honest)[:3]  # offer, counter, offer: the same
    assert moves(broken)[3] == ("blocked", 560)  # half of Ralph's £11.20, and never sent
    assert len(moves(broken)) == 4
    blocked = broken["steps"][-1]
    assert blocked["say"].startswith("This Tommy is broken on purpose")
    assert "card_outside_limit" in blocked["detail"]


def test_bad_input_is_refused() -> None:
    with pytest.raises(ValueError, match="multiple of 50"):
        RoomInput(Pence(1550), Pence(935), pairs=75)
    with pytest.raises(ValueError, match="between 1p and £100"):
        RoomInput(Pence(0), Pence(935))
    with pytest.raises(BadRequest):
        read_input({"buyer_max": 1550})
    with pytest.raises(BadRequest):
        read_input({"buyer_max": "lots", "seller_floor": 935})


# The server, on a free port on this computer.


@pytest.fixture
def server(settings: Settings) -> Iterator[str]:
    srv = make_server(Room(settings, lambda: (ScriptedRalph(), ScriptedTommy())), port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def call(url: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        raw, status = error.read(), error.code
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw.decode()


def test_the_server_serves_the_page_and_nothing_outside_its_folder(server: str) -> None:
    status, page = call(server + "/")
    assert status == 200 and "<title>Deal Room</title>" in page
    status, _ = call(server + "/static/../../../pyproject.toml")
    assert status == 404
    status, _ = call(server + "/elsewhere")
    assert status == 404


def test_the_page_loads_everything_from_this_computer(server: str) -> None:
    """No CDN, no fonts from the web: the demo has to work without wifi."""
    status, page = call(server + "/")
    assert status == 200
    for asset in re.findall(r'(?:src|href)="([^"]+)"', page):
        assert asset.startswith("/static/"), asset
        with urllib.request.urlopen(server + asset, timeout=10) as response:
            assert response.status == 200
            kind = response.headers["Content-Type"]
        assert kind.startswith({"js": "text/javascript", "css": "text/css"}[asset.split(".")[-1]])
    script = (ROOT / "src/fleek_agents/room/static/room.js").read_text(encoding="utf-8")
    assert not re.search(r"https?://", script)


def test_three_js_keeps_its_licence_header() -> None:
    head = (ROOT / "src/fleek_agents/room/static/three.min.js").read_text(encoding="utf-8")[:120]
    assert "Three.js Authors" in head and "MIT" in head


def test_run_then_approve_closes_the_deal_across_requests(server: str) -> None:
    status, s = call(server + "/api/run", {"buyer_max": 1550, "seller_floor": 935})
    assert status == 200 and s["outcome"]["state"] == "pending_approval"
    status, answer = call(server + "/api/decide", {"decision": "approve"})
    assert status == 200 and answer["state"] == "closed"
    status, answer = call(server + "/api/decide", {"decision": "approve"})
    assert status == 400 and "isn't waiting" in answer["error"]


def test_reject_puts_the_deal_back(server: str) -> None:
    call(server + "/api/run", {"buyer_max": 1550, "seller_floor": 935})
    status, answer = call(server + "/api/decide", {"decision": "reject"})
    assert status == 200 and answer["state"] == "rejected_by_human"


def test_the_server_lists_the_scenarios_with_their_inputs(server: str) -> None:
    status, answer = call(server + "/api/scenarios")
    assert status == 200
    assert [x["key"] for x in answer["scenarios"]] == [x.key for x in SCENARIOS]
    broken = next(x for x in answer["scenarios"] if x["key"] == "broken")
    status, s = call(server + "/api/run", broken["input"])
    assert status == 200 and s["outcome"]["state"] == "needs_human"
    assert s["input"]["tommy_breaks_a_rule"] is True


def test_the_server_answers_bad_requests_with_a_reason(server: str) -> None:
    status, answer = call(server + "/api/decide", {"decision": "approve"})
    assert status == 400 and answer["error"] == "No deal to decide on yet."
    status, answer = call(server + "/api/run", {"buyer_max": 1550, "seller_floor": 935, "pairs": 7})
    assert status == 400 and "multiple of 50" in answer["error"]
    status, answer = call(server + "/api/run", {"buyer_max": 1550})
    assert status == 400


def test_fleek_room_says_when_its_port_is_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        result = CliRunner().invoke(app, ["room", "--port", str(port), "--no-open"])
    assert result.exit_code == 2
    assert f"Port {port} is busy" in result.output
