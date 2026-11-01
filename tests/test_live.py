import json
from collections.abc import Iterator
from typing import Any

import pytest

from fleek_agents.agents.base import Agent, View, WalkAway
from fleek_agents.agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.config import Settings
from fleek_agents.live.forms import PRESET, FormError, Setup
from fleek_agents.live.session import LiveSession, build

SETTINGS = Settings().model_copy(
    update={
        "privacy": Settings().privacy.model_copy(update={"on": True}),
        "match_gate": Settings().match_gate.model_copy(update={"on": True}),
    }
)


def setup(**changes: Any) -> Setup:
    data = json.loads(json.dumps(PRESET))
    for path, value in changes.items():
        *where, key = path.split("__")
        node: Any = data
        for part in where:
            node = node[int(part)] if part.isdigit() else node[part]
        node[key] = value
    return Setup.model_validate(data)


def scripted() -> tuple[ScriptedRalph, ScriptedTommy]:
    return ScriptedRalph(), ScriptedTommy()


def run(live: LiveSession) -> LiveSession:
    while live.step():
        pass
    return live


def test_a_secret_typed_where_an_agent_reads_is_refused() -> None:
    with pytest.raises(FormError, match="Ralph reads it"):
        build(setup(buyer__notes="I can go to £15.50 if needed"), SETTINGS)
    with pytest.raises(FormError, match="Ralph reads it"):
        build(setup(buyer__notes="around 1500p"), SETTINGS)
    with pytest.raises(FormError, match="secret number"):
        build(setup(seller__stock__0__description="Floor is 9.35, don't tell"), SETTINGS)
    build(setup(seller__stock__0__description="Some fading, priced to sell."), SETTINGS)


def test_a_firm_price_or_an_offer_below_the_floor_is_refused_to_the_seller() -> None:
    with pytest.raises(FormError, match="floor"):
        build(setup(seller__stock__1__firm_price=1500), SETTINGS)
    with pytest.raises(FormError, match="floor"):
        build(setup(seller__stock__0__walkaway_offer_pct=40), SETTINGS)


def test_each_screen_shows_only_its_own_side_s_secret() -> None:
    live = run(LiveSession(setup(), SETTINGS, scripted, "test"))
    view = live.view()
    buyer, seller, fleek = (
        json.dumps(view[k], ensure_ascii=False) for k in ("buyer", "seller", "fleek")
    )
    assert "£15.50" in buyer and "£15.50" not in seller and "£15.50" not in fleek
    assert "£9.35" in seller and "£9.35" not in buyer and "£9.35" not in fleek
    assert view["state"] == "pending_approval"
    assert view["buyer"]["asked"] and view["fleek"]["asked"] and not view["seller"]["asked"]


def test_the_people_asked_close_the_deal() -> None:
    live = run(LiveSession(setup(), SETTINGS, scripted, "test"))
    live.decide("buyer", "approve")
    assert live.view()["state"] == "pending_approval"
    with pytest.raises(FormError):  # the seller chose to let Tommy close, so isn't asked
        live.decide("seller", "approve")
    live.decide("account_manager", "approve")
    assert live.view()["state"] == "closed"


def test_pause_holds_it_and_stop_ends_it() -> None:
    live = LiveSession(setup(), SETTINGS, scripted, "test")
    live.step()
    live.control("pause", "buyer")
    assert live.step() is False
    live.control("resume", "buyer")
    assert live.step() is True
    live.control("stop", "seller")
    view = live.view()
    assert view["state"] == "stopped" and view["over"]


class Leaves:
    def decide(self, view: View) -> WalkAway:
        return WalkAway()


def test_a_buyer_who_walks_away_gets_the_seller_s_offer_and_code_keeps_it() -> None:
    agents: Iterator[tuple[Agent, Agent]] = iter(
        [(Leaves(), ScriptedTommy()), (ScriptedRalph(), ScriptedTommy())]
    )
    # A top price that covers the offer: £12.85 + £3.00 shipping + 2% fee is about £16.17.
    live = run(LiveSession(setup(buyer__top_price=1650), SETTINGS, lambda: next(agents), "test"))
    lines = [line.text for line in live.lines]
    assert any("standing offer goes out: 8% off, £12.85" in t for t in lines)
    assert live.view()["state"] == "pending_approval"
    assert live.log.saved(live.nid).agreed.base_price.value == 1285  # type: ignore[arg-type, union-attr]


def test_no_lot_that_fits_means_no_agent_is_called() -> None:
    def no_agents() -> tuple[ScriptedRalph, ScriptedTommy]:
        raise AssertionError("no agent should be made")

    live = LiveSession(setup(buyer__category="shoes"), SETTINGS, no_agents, "test")
    assert live.view()["state"] == "no_match" and live.step() is False
