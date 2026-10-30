import random

import pytest
from pydantic import ValidationError

from fleek_agents.domain.money import Pence
from fleek_agents.vault.bands import Band, BandThresholds, band_of, buyer_band, seller_band
from fleek_agents.vault.checks import buyer_ok, seller_ok
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate
from fleek_agents.vault.secret import SecretMoney

DEFAULT = BandThresholds()
BUYER = BuyerMandate(buyer_id="buyer-0001", max_per_piece=SecretMoney(Pence(1000)))
SELLER = SellerMandate(seller_id="seller-01", floor_per_piece=SecretMoney(Pence(850)))


@pytest.mark.parametrize(
    ("cost", "band"),
    [
        (500, Band.STRONG),
        (850, Band.STRONG),  # exactly 85% of the max
        (851, Band.ACCEPTABLE),
        (950, Band.ACCEPTABLE),
        (951, Band.STRETCH),
        (1000, Band.STRETCH),  # exactly the max is still allowed
        (1001, Band.OUTSIDE),  # a penny over is not
    ],
)
def test_a_buyer_hears_how_close_a_price_is_to_their_max(cost: int, band: Band) -> None:
    assert band_of(Pence(cost), Pence(1000), DEFAULT) is band  # against a £10.00 limit


@pytest.mark.parametrize(
    ("proceeds", "band"),
    [
        (1000, Band.STRONG),  # the floor is 85% of this
        (999, Band.ACCEPTABLE),
        (895, Band.ACCEPTABLE),  # floor is just under 95% of this
        (894, Band.STRETCH),
        (850, Band.STRETCH),  # exactly the floor is still allowed
        (849, Band.OUTSIDE),
    ],
)
def test_a_seller_hears_how_close_a_price_is_to_their_floor(proceeds: int, band: Band) -> None:
    assert band_of(Pence(850), Pence(proceeds), DEFAULT) is band  # an £8.50 floor


def test_thresholds_change_the_bands() -> None:
    tight = BandThresholds(strong_pct=70, acceptable_pct=90)
    assert band_of(Pence(800), Pence(1000), tight) is Band.ACCEPTABLE


@pytest.mark.parametrize(
    "bad", [{"strong_pct": 95, "acceptable_pct": 85}, {"strong_pct": 0}, {"acceptable_pct": 100}]
)
def test_thresholds_that_dont_make_sense_are_refused(bad: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        BandThresholds.model_validate(bad)


def test_a_band_is_a_word_never_a_number() -> None:
    assert {band.value for band in Band} == {"strong", "acceptable", "stretch", "outside"}


def test_a_mandate_never_shows_its_secret() -> None:
    assert "1000" not in repr(BUYER)
    assert "850" not in f"{SELLER}"


def test_bands_count_fees_like_the_yes_no_checks_do() -> None:
    # 100 x (£12.83 + £3.00) plus the £20 capped fee is £1,603.00: exactly a £16.03 max.
    b = BuyerMandate(buyer_id="buyer-0001", max_per_piece=SecretMoney(Pence(1603)))
    band = buyer_band(b, base_price=Pence(1283), shipping=Pence(300), pieces=100, t=DEFAULT)
    assert band is Band.STRETCH


def test_outside_means_exactly_what_the_yes_no_checks_refuse() -> None:
    rng = random.Random(14)
    for _ in range(2000):
        price, ship, pieces = (
            Pence(rng.randint(0, 3000)),
            Pence(rng.randint(0, 500)),
            rng.randint(1, 200),
        )
        b = BuyerMandate(
            buyer_id="buyer-0001", max_per_piece=SecretMoney(Pence(rng.randint(0, 4000)))
        )
        s = SellerMandate(
            seller_id="seller-01", floor_per_piece=SecretMoney(Pence(rng.randint(0, 3000)))
        )
        b_band = buyer_band(b, base_price=price, shipping=ship, pieces=pieces, t=DEFAULT)
        s_band = seller_band(s, base_price=price, pieces=pieces, t=DEFAULT)
        assert (b_band is Band.OUTSIDE) is not buyer_ok(
            b, base_price=price, shipping=ship, pieces=pieces
        )
        assert (s_band is Band.OUTSIDE) is not seller_ok(s, base_price=price, pieces=pieces)
