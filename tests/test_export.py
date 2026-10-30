import json
from typing import Any

import pytest
from pydantic import BaseModel

from fleek_agents.agents.scripted import ScriptedRalph
from fleek_agents.config import Settings
from fleek_agents.domain.money import Pence
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.run import run_parallel
from fleek_agents.safety.leaks import find_amounts, is_near
from fleek_agents.trace.export import RunTrace, export_run
from fleek_agents.vault.secret import SecretMoney
from tests.test_parallel import LOTS, SECRETS, WANT, three_deals
from tests.test_scripted import T0


@pytest.fixture(scope="module")
def trace() -> RunTrace:
    log, deals = three_deals(ScriptedRalph(), SECRETS.buyers[WANT.buyer_id])
    run_parallel(log, deals, clock=FakeClock(T0), settings=Settings())
    return export_run(log, [d.negotiation_id for d in deals], LOTS, title="buyer-0001, three deals")


def test_a_run_exports_every_move_of_every_negotiation(trace: RunTrace) -> None:
    assert len(trace.negotiations) == 3
    for negotiation in trace.negotiations:
        assert negotiation.moves[0].move == "start"
        assert negotiation.outcome in {
            "pending_approval",
            "walked_away",
            "needs_human",
            "lost_to_other_buyer",
        }
    cards = [m for n in trace.negotiations for m in n.moves if m.price_pence is not None]
    assert cards and all(m.who in {"ralph", "tommy"} for m in cards)


def numbers(node: object) -> list[int]:
    """Every amount in the file: whole numbers, and prices written inside text ("£9.50")."""
    if isinstance(node, bool):
        return []
    if isinstance(node, int):
        return [node]
    if isinstance(node, str):
        return [amount.value for amount in find_amounts(node)]
    if isinstance(node, dict):
        return [n for v in node.values() for n in numbers(v)]
    if isinstance(node, list):
        return [n for v in node for n in numbers(v)]
    return []


def secret_numbers(data: dict[str, Any]) -> list[str]:
    """Amounts in an exported run that equal, or come within 2% of, a secret limit."""
    found = []
    for negotiation in data["negotiations"]:
        floor = SECRETS.lots[negotiation["lot_id"]].floor_per_piece.reveal()
        buyer = SECRETS.buyers[negotiation["buyer_id"]]
        secrets = [floor, Pence(-(-floor.value * 100 // 85)), buyer.max_per_piece.reveal()]
        if buyer.budget is not None:
            secrets.append(buyer.budget.reveal())
        public = {m["price_pence"] for m in negotiation["moves"]}
        public |= {negotiation["lot"]["list_price_pence"], negotiation["lot"]["shipping_pence"]}
        for n in numbers(negotiation):
            if n in public or n <= 0:
                continue
            if any(is_near(Pence(n), s) for s in secrets):
                found.append(f"{n} in {negotiation['id']}")
    return found


def test_no_number_in_the_file_is_a_secret_limit(trace: RunTrace) -> None:
    assert secret_numbers(json.loads(trace.model_dump_json())) == []
    text = trace.model_dump_json()
    assert "floor" not in text and "max_per_piece" not in text and "budget" not in text


@pytest.mark.parametrize("which", ["floor", "max", "budget"])
def test_the_check_finds_a_secret_written_inside_text(trace: RunTrace, which: str) -> None:
    data = json.loads(trace.model_dump_json())
    negotiation = data["negotiations"][0]
    buyer = SECRETS.buyers[negotiation["buyer_id"]]
    assert buyer.budget is not None
    secret = {
        "floor": SECRETS.lots[negotiation["lot_id"]].floor_per_piece,
        "max": buyer.max_per_piece,
        "budget": buyer.budget,
    }[which].reveal()
    negotiation["lot"]["title"] += f" (only {secret})"  # written as pounds, inside text
    assert secret_numbers(data) == [f"{secret.value} in {negotiation['id']}"]


def test_a_secret_can_t_be_added_to_the_trace_by_mistake() -> None:
    with pytest.raises(TypeError):

        class Leaky(BaseModel):
            floor: SecretMoney


def test_the_file_is_plain_json(trace: RunTrace) -> None:
    data = json.loads(trace.model_dump_json())
    assert data["format"] == "ralph-and-tommy/run/1"
