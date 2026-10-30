import random

import pytest

from fleek_agents.domain.money import Pence
from fleek_agents.domain.rules import Quote
from fleek_agents.vault.checks import can_accept, deal_possible
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate
from fleek_agents.vault.secret import SecretMoney


def buyer(max_pence: int) -> BuyerMandate:
    return BuyerMandate(buyer_id="buyer-0001", max_per_piece=SecretMoney(Pence(max_pence)))


def seller(floor_pence: int) -> SellerMandate:
    return SellerMandate(seller_id="seller-01", floor_per_piece=SecretMoney(Pence(floor_pence)))


def quote(base: int, shipping: int = 300, pieces: int = 100) -> Quote:
    return Quote(
        lot_id="lot-0001",
        bundles=1,
        pieces=pieces,
        percent_off=0,
        base_price=Pence(base),
        shipping=Pence(shipping),
        total=(Pence(base) + Pence(shipping)).times(pieces),
    )


# The 501s: 100 pieces at £12.83 + £3.00. The buyer pays £1,603.00 (£16.03 a piece, fee
# included); the seller nets £1,090.55 (£10.9055 a piece).
@pytest.mark.parametrize(
    ("max_pence", "floor_pence", "ok"),
    [
        (1603, 1090, True),  # both exactly inside
        (1602, 1090, False),  # a penny short of what the buyer would pay
        (1603, 1091, False),  # the seller would net less than their floor
    ],
)
def test_can_accept_checks_both_limits_on_the_money_that_moves(
    max_pence: int, floor_pence: int, ok: bool
) -> None:
    answer = can_accept(
        buyer(max_pence),
        seller(floor_pence),
        base_price=Pence(1283),
        shipping=Pence(300),
        pieces=100,
    )
    assert answer is ok


def test_a_deal_that_cant_work_at_any_price_is_spotted() -> None:
    # The seller needs about £9.42 base to net £8.00; with £3.00 shipping and the fee
    # the buyer would pay over £12.00 a piece, but their max is £10.00.
    assert deal_possible(buyer(1000), seller(800), quote(base=1500)) is False


def test_a_deal_that_can_work_is_spotted() -> None:
    assert deal_possible(buyer(1400), seller(800), quote(base=1500)) is True


def test_no_deal_if_the_floor_is_above_the_listed_price() -> None:
    assert (
        deal_possible(buyer(5000), seller(1400), quote(base=1500)) is False
    )  # 85% of 15.00 < 14.00


def _brute_force(b: BuyerMandate, s: SellerMandate, q: Quote) -> bool:
    return any(
        can_accept(b, s, base_price=Pence(p), shipping=q.shipping, pieces=q.pieces)
        for p in range(q.base_price.value + 1)
    )


def test_deal_possible_agrees_with_trying_every_price() -> None:
    rng = random.Random(15)
    for _ in range(300):
        q = quote(
            base=rng.randint(0, 600), shipping=rng.randint(0, 200), pieces=rng.randint(1, 120)
        )
        b, s = buyer(rng.randint(0, 900)), seller(rng.randint(0, 600))
        assert deal_possible(b, s, q) is _brute_force(b, s, q)
