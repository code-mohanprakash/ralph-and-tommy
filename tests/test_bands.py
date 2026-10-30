import pytest
from pydantic import ValidationError

from fleek_agents.domain.money import Pence
from fleek_agents.vault.bands import Band, BandThresholds, buyer_band, seller_band
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
    assert buyer_band(BUYER, Pence(cost), DEFAULT) is band


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
    assert seller_band(SELLER, Pence(proceeds), DEFAULT) is band


def test_thresholds_change_the_bands() -> None:
    tight = BandThresholds(strong_pct=70, acceptable_pct=90)
    assert buyer_band(BUYER, Pence(800), tight) is Band.ACCEPTABLE


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
