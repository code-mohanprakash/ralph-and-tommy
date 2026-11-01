from dataclasses import replace

import pytest
from pydantic import ValidationError

from fleek_agents.bench.scenarios import Scenario, generate
from fleek_agents.domain.models import Lot, SellMode
from fleek_agents.domain.money import Pence
from fleek_agents.vault.checks import seller_ok
from fleek_agents.vault.firm import FirmBelowFloor, check_firm_price, working_limit
from fleek_agents.vault.mandate import SellerMandate
from fleek_agents.vault.secret import SecretMoney

SCENARIO = generate(1)[0]


def firm_lot(lot: Lot, price: int) -> Lot:
    return Lot.model_validate(lot.model_dump() | {"sell_mode": SellMode.FIRM, "firm_price": price})


def with_floor(limit: SellerMandate, floor: int) -> SellerMandate:
    return replace(limit, floor_per_piece=SecretMoney(Pence(floor)))


def firm_price_above_both(scenario: Scenario) -> int:
    return scenario.lot.base_price.value * 95 // 100 // 5 * 5


def test_firm_mode_and_a_firm_price_go_together() -> None:
    data = SCENARIO.lot.model_dump()
    with pytest.raises(ValidationError):
        Lot.model_validate(data | {"sell_mode": SellMode.FIRM})
    with pytest.raises(ValidationError):
        Lot.model_validate(data | {"firm_price": 1000})
    with pytest.raises(ValidationError):  # above the list price
        Lot.model_validate(
            data | {"sell_mode": SellMode.FIRM, "firm_price": SCENARIO.lot.base_price.value + 5}
        )


def test_a_firm_price_below_the_floor_is_refused_when_set() -> None:
    lot, limit = SCENARIO.lot, SCENARIO.seller_limit
    lowest = SCENARIO.truth.seller_min.value
    check_firm_price(limit, Pence(lowest), pieces=lot.pieces)
    with pytest.raises(FirmBelowFloor):
        check_firm_price(limit, Pence(lowest - 1), pieces=lot.pieces)
    with pytest.raises(FirmBelowFloor):  # and a lot listed that way is refused, not fudged
        working_limit(limit, firm_lot(lot, lowest - 5))


def test_in_firm_mode_every_yes_or_no_is_the_same_whatever_the_floor() -> None:
    for scenario in generate(50):
        lot = scenario.lot
        firm = firm_price_above_both(scenario)
        floor = scenario.seller_limit.floor_per_piece.reveal().value
        lower = with_floor(scenario.seller_limit, floor // 2)
        if firm < scenario.truth.seller_min.value:
            continue  # this seller couldn't pick that firm price
        listed = firm_lot(lot, firm)
        a = working_limit(scenario.seller_limit, listed)
        b = working_limit(lower, listed)
        for price in range(0, lot.base_price.value + 1, 1):
            p = Pence(price)
            same = seller_ok(a, base_price=p, pieces=lot.pieces) == seller_ok(
                b, base_price=p, pieces=lot.pieces
            )
            assert same, (scenario.key, price)
        # and the answer is exactly "at or above the firm price"
        assert seller_ok(a, base_price=Pence(firm), pieces=lot.pieces)
        assert not seller_ok(a, base_price=Pence(firm - 1), pieces=lot.pieces)


def test_haggle_mode_still_uses_the_floor() -> None:
    limit = SCENARIO.seller_limit
    assert working_limit(limit, SCENARIO.lot) is limit


def test_matching_gives_the_same_answer_whatever_the_floor() -> None:
    from fleek_agents.domain.rules import quote
    from fleek_agents.vault.checks import deal_possible

    for scenario in generate(50):
        firm = firm_price_above_both(scenario)
        if firm < scenario.truth.seller_min.value:
            continue
        listed = firm_lot(scenario.lot, firm)
        q = quote(listed, scenario.seller, bundles=1)
        floor = scenario.seller_limit.floor_per_piece.reveal().value
        answers = {
            deal_possible(
                scenario.buyer, working_limit(with_floor(scenario.seller_limit, f), listed), q
            )
            for f in (floor, floor // 2, floor * 3 // 4)
        }
        assert len(answers) == 1, scenario.key


def _run(scenario: Scenario, lot: Lot, limit: SellerMandate) -> list[tuple[object, ...]]:
    """One scripted negotiation; returns everything the buyer can see, event by event."""
    from datetime import UTC, datetime

    from sqlalchemy.orm import Session

    from fleek_agents.config import Settings
    from fleek_agents.orchestrator.clock import FakeClock
    from fleek_agents.orchestrator.opening import open_negotiation
    from fleek_agents.orchestrator.run import run_negotiation
    from fleek_agents.scripted import ScriptedRalph, ScriptedTommy
    from fleek_agents.store.db import Base, make_engine
    from fleek_agents.store.deals import put_on_sale
    from fleek_agents.store.events import EventLog

    settings = Settings()
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        log, clock = EventLog(session), FakeClock(datetime(2026, 11, 2, 9, tzinfo=UTC))
        put_on_sale(session, lot.id, bundles=1)
        nid = open_negotiation(
            log,
            buyer_id=scenario.want.buyer_id,
            lot_id=lot.id,
            clock=clock,
            rules=settings.negotiation,
        )
        run_negotiation(
            log,
            nid,
            lot=lot,
            seller=scenario.seller,
            want=scenario.want,
            bundles=1,
            buyer_limit=scenario.buyer,
            seller_limit=limit,
            ralph=ScriptedRalph(),
            tommy=ScriptedTommy(),
            clock=clock,
            settings=settings,
        )
        return [(e.move, e.by, e.at, e.to_state, e.card, e.reason) for e in log.read(nid)]


def test_a_whole_negotiation_looks_the_same_to_the_buyer_whatever_the_floor() -> None:
    compared = deals = 0
    for scenario in generate(60):
        firm = firm_price_above_both(scenario)
        if firm < scenario.truth.seller_min.value:
            continue
        listed = firm_lot(scenario.lot, firm)
        floor = scenario.seller_limit.floor_per_piece.reveal().value
        runs = [
            _run(scenario, listed, with_floor(scenario.seller_limit, f))
            for f in (floor, floor // 2, floor * 9 // 10)
        ]
        assert runs[0] == runs[1] == runs[2], scenario.key
        compared += 1
        deals += any(step[0] == "accept" for step in runs[0])
    assert compared >= 20 and deals > 0  # the comparison covered deals, not just walk-aways


def test_in_haggle_mode_the_floor_does_change_what_the_buyer_sees() -> None:
    # The control: without firm mode, the same comparison finds differences.
    differs = 0
    for scenario in generate(30):
        floor = scenario.seller_limit.floor_per_piece.reveal().value
        a = _run(scenario, scenario.lot, scenario.seller_limit)
        b = _run(scenario, scenario.lot, with_floor(scenario.seller_limit, floor * 9 // 10))
        differs += a != b
    assert differs > 0


def test_claude_agents_get_byte_identical_requests_whatever_the_floor() -> None:
    """What reaches the model is all it could ever leak; in firm mode it doesn't move."""
    import json
    from datetime import UTC, datetime

    from sqlalchemy.orm import Session

    from fleek_agents.agents.claude import ClaudeAgent
    from fleek_agents.config import Settings
    from fleek_agents.orchestrator.clock import FakeClock
    from fleek_agents.orchestrator.opening import open_negotiation
    from fleek_agents.orchestrator.run import run_negotiation
    from fleek_agents.store.db import Base, make_engine
    from fleek_agents.store.deals import put_on_sale
    from fleek_agents.store.events import EventLog
    from tests.fakes import FakeClient, call, message

    scenario = next(  # a lot where the firm price clears the floor and the buyer can pay it
        s
        for s in generate(40)
        if s.truth.seller_min.value <= firm_price_above_both(s) <= s.truth.buyer_max.value
    )
    firm = firm_price_above_both(scenario)
    listed = firm_lot(scenario.lot, firm)
    offer = {"price_pence": firm, "prepaid": False, "reason_codes": []}

    def requests(floor: int) -> str:
        ralph_client = FakeClient(
            message(call("get_lot", {})),
            message(call("check_price", {"price_pence": firm})),
            message(call("send_offer", offer)),
        )
        tommy_client = FakeClient(
            message(call("check_price", {"price_pence": firm})), message(call("accept", {}))
        )
        settings = Settings()
        engine = make_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            log, clock = EventLog(session), FakeClock(datetime(2026, 11, 2, 9, tzinfo=UTC))
            put_on_sale(session, listed.id, bundles=1)
            nid = open_negotiation(
                log,
                buyer_id=scenario.want.buyer_id,
                lot_id=listed.id,
                clock=clock,
                rules=settings.negotiation,
            )
            run_negotiation(
                log,
                nid,
                lot=listed,
                seller=scenario.seller,
                want=scenario.want,
                bundles=1,
                buyer_limit=scenario.buyer,
                seller_limit=with_floor(scenario.seller_limit, floor),
                ralph=ClaudeAgent(ralph_client, model="claude-haiku-5-5", prompt="ralph"),
                tommy=ClaudeAgent(tommy_client, model="claude-haiku-5-5", prompt="tommy"),
                clock=clock,
                settings=settings,
            )
            assert log.saved(nid).agreed is not None
        return json.dumps([ralph_client.requests, tommy_client.requests], default=str)

    floor = scenario.seller_limit.floor_per_piece.reveal().value
    seen = requests(floor)
    assert str(firm) in seen  # the firm price is public, so it's there
    assert requests(floor // 2) == seen


def test_the_bench_finds_the_floor_shows_when_haggling_and_never_in_firm_mode() -> None:
    from fleek_agents.bench.firm import firm_report
    from fleek_agents.config import Settings

    haggle, *firm = firm_report(Settings(), count=30)
    assert haggle.floor_shows > 0
    assert all(row.floor_shows == 0 and row.lots > 0 for row in firm)
    assert all(row.deals.value < haggle.deals.value for row in firm)  # and it costs deals
