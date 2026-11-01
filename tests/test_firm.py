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
