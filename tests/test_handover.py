"""The account manager's summary: written whenever a person is needed, never holding a secret."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fleek_agents.agents.base import Action, Send, View
from fleek_agents.agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.cli import app
from fleek_agents.config import Settings, load_settings
from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.money import Pence
from fleek_agents.humans.handover import STOPPED
from fleek_agents.room.play import run_room
from fleek_agents.room.scenario import SCENARIOS, RoomInput

ROOT = Path(__file__).parent.parent
SCENARIO = {x.key: x for x in SCENARIOS}


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings(ROOT / "market.toml")


@pytest.mark.parametrize(
    ("key", "kind"),
    [
        ("deal", "approve"),
        ("small", None),  # approved by the rule: nobody needs to look
        ("broken", "stopped"),
        ("near_miss", "near_miss"),
        ("no_match", None),  # never matched: nothing to call about
    ],
)
def test_a_summary_is_written_exactly_when_a_person_is_needed(
    settings: Settings, key: str, kind: str | None
) -> None:
    run = run_room(
        SCENARIO[key].room, ralph=ScriptedRalph(), tommy=ScriptedTommy(), settings=settings
    )
    assert (run.handover.kind if run.handover else None) == kind


@pytest.mark.parametrize("key", ["deal", "broken", "near_miss"])
def test_a_summary_never_holds_a_secret_limit(settings: Settings, key: str) -> None:
    room = SCENARIO[key].room
    run = run_room(room, ralph=ScriptedRalph(), tommy=ScriptedTommy(), settings=settings)
    assert run.handover is not None
    text = json.dumps(asdict(run.handover), default=str, ensure_ascii=False)
    edges = [run.limits.buyer_highest, run.limits.seller_lowest]
    cards = {e.card.base_price for e in run.log.read(run.negotiation_id or "") if e.card}
    for secret in [room.buyer_max, room.seller_floor, *[p for p in edges if p and p not in cards]]:
        pounds = f"{secret.value // 100}.{secret.value % 100:02d}"
        assert pounds not in text, f"{secret} is in the summary"


def test_the_approval_summary_says_what_is_at_stake(settings: Settings) -> None:
    run = run_room(
        SCENARIO["deal"].room, ralph=ScriptedRalph(), tommy=ScriptedTommy(), settings=settings
    )
    h = run.handover
    assert h is not None
    assert h.why == "An agreed deal waits for your OK: £1,500 or more."
    assert h.at_stake == Pence(304000)
    assert "£12.10 a piece for 200 pieces" in h.stands
    assert h.happened[-1] == "Tommy accepted"
    assert len(h.happened) == 6  # five cards and the accept


def test_the_near_miss_summary_gives_the_gap(settings: Settings) -> None:
    run = run_room(
        SCENARIO["near_miss"].room, ralph=ScriptedRalph(), tommy=ScriptedTommy(), settings=settings
    )
    h = run.handover
    assert h is not None
    assert "2% apart" in h.why
    assert "£13.05" in h.stands and "£13.35" in h.stands and "£0.30 a piece apart" in h.stands
    assert h.todo.startswith("Call the seller first")


class GreedyRalph:
    """A Ralph broken on purpose: his second offer is £50 a pair, far past any max here."""

    def __init__(self) -> None:
        self._inner, self._offers = ScriptedRalph(), 0

    def decide(self, view: View) -> Action:
        action = self._inner.decide(view)
        if isinstance(action, Send):
            self._offers += 1
            if self._offers == 2:
                return Send(terms=action.terms.model_copy(update={"base_price": Pence(5000)}))
        return action


def test_a_stop_on_the_buyers_side_sends_the_call_to_the_buyer(settings: Settings) -> None:
    room = RoomInput(buyer_max=Pence(1550), seller_floor=Pence(935))
    run = run_room(room, ralph=GreedyRalph(), tommy=ScriptedTommy(), settings=settings)
    h = run.handover
    assert h is not None and h.kind == "stopped"
    assert h.why.startswith("Ralph (buyer's agent) tried to send a card past")
    assert h.todo.startswith("Call the buyer")
    assert "On the table: Tommy's £14.00" in h.stands


def test_the_seller_side_stop_sends_the_call_to_the_seller(settings: Settings) -> None:
    run = run_room(
        SCENARIO["broken"].room, ralph=ScriptedRalph(), tommy=ScriptedTommy(), settings=settings
    )
    h = run.handover
    assert h is not None
    assert h.why.startswith("Tommy (seller's agent) tried to send a card past")
    assert h.todo.startswith("Call the seller")
    assert "On the table: Ralph's £11.20" in h.stands


def test_every_reason_to_stop_has_advice() -> None:
    assert set(STOPPED) == set(EscalationReason)


def test_fleek_summary_prints_the_summary_from_a_deals_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    db = str(tmp_path / "f.db")
    runner = CliRunner()
    runner.invoke(
        app, ["negotiate", "--mock", "--buyer", "buyer-0002", "--matcher", "words", "--db", db]
    )
    result = runner.invoke(app, ["summary", "neg-0001", "--db", db])
    assert result.exit_code == 0, result.output
    assert (
        "Why you're seeing this: An agreed deal waits for your OK: £1,500 or more." in result.output
    )
    assert "1. Ralph offered £5.60 a piece" in result.output
    missing = runner.invoke(app, ["summary", "neg-0099", "--db", db])
    assert missing.exit_code == 2 and "No negotiation called neg-0099" in missing.output
