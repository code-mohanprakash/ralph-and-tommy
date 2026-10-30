import pytest

from fleek_agents.domain.fees import buyer_pays, seller_receives
from fleek_agents.domain.money import Pence


def test_the_501s_worked_example() -> None:
    # 100 Levi's 501s at £12.83 base (after 5% bulk) + £3.00 shipping per piece.
    order = buyer_pays(base_price=Pence(1283), shipping=Pence(300), pieces=100)
    assert order.goods == Pence(158_300)  # £1,583.00
    assert order.protection_fee == Pence(2000)  # 2% would be £31.66; capped at £20
    assert order.total == Pence(160_300)  # £1,603.00

    payout = seller_receives(base_price=Pence(1283), pieces=100)
    assert payout.gross == Pence(128_300)  # shipping isn't the seller's income
    assert payout.commission == Pence(19_245)  # 15%
    assert payout.net == Pence(109_055)  # £1,090.55


def test_a_small_order_pays_the_full_two_percent() -> None:
    order = buyer_pays(base_price=Pence(1350), shipping=Pence(300), pieces=50)
    assert order.goods == Pence(82_500)
    assert order.protection_fee == Pence(1650)  # £16.50, under the cap
    assert order.total == Pence(84_150)


def test_commission_rounds_half_a_penny_up() -> None:
    payout = seller_receives(base_price=Pence(3), pieces=1)  # 15% of 3p is 0.45p
    assert (payout.commission, payout.net) == (Pence(0), Pence(3))
    payout = seller_receives(base_price=Pence(10), pieces=1)  # 15% of 10p is 1.5p
    assert (payout.commission, payout.net) == (Pence(2), Pence(8))


@pytest.mark.parametrize("pieces", [0, -1])
def test_an_order_needs_pieces(pieces: int) -> None:
    with pytest.raises(ValueError):
        buyer_pays(base_price=Pence(1000), shipping=Pence(300), pieces=pieces)
    with pytest.raises(ValueError):
        seller_receives(base_price=Pence(1000), pieces=pieces)
