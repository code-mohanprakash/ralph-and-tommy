import pytest
from pydantic import ValidationError

from fleek_agents.domain.models import BulkRules, BulkTier, Lot, Seller
from fleek_agents.domain.money import Pence
from fleek_agents.domain.rules import quote


def tiers(*pairs: tuple[int, int]) -> BulkRules:
    return BulkRules(tiers=tuple(BulkTier(min_pieces=m, percent_off=p) for m, p in pairs))


RULES = tiers((100, 5), (200, 10))


@pytest.mark.parametrize(
    ("pieces", "percent"), [(1, 0), (99, 0), (100, 5), (199, 5), (200, 10), (5000, 10)]
)
def test_the_biggest_tier_reached_applies(pieces: int, percent: int) -> None:
    assert RULES.percent_off(pieces) == percent


def test_no_tiers_means_no_discount() -> None:
    assert BulkRules().percent_off(500) == 0


@pytest.mark.parametrize(
    "pairs",
    [
        ((200, 10), (100, 5)),  # out of order
        ((100, 5), (100, 8)),  # the same size twice
        ((100, 10), (200, 5)),  # buying more would cost more per piece
    ],
)
def test_tiers_that_dont_make_sense_are_refused(pairs: tuple[tuple[int, int], ...]) -> None:
    with pytest.raises(ValidationError):
        tiers(*pairs)


@pytest.mark.parametrize("bad", [{"min_pieces": 0}, {"percent_off": 101}, {"percent_off": -1}])
def test_a_tier_with_bad_numbers_is_refused(bad: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        BulkTier.model_validate({"min_pieces": 100, "percent_off": 5} | bad)


def test_a_seller_carries_their_bulk_rules() -> None:
    seller = Seller.model_validate(
        {
            "id": "seller-01",
            "name": "Karachi Denim Co",
            "country": "PK",
            "quality_score": 4.6,
            "dispatch_days": 2,
            "bulk_rules": {"tiers": [{"min_pieces": 100, "percent_off": 5}]},
        }
    )
    assert seller.bulk_rules.percent_off(100) == 5


SELLER = Seller.model_validate(
    {
        "id": "seller-01",
        "name": "Karachi Denim Co",
        "country": "PK",
        "quality_score": 4.6,
        "dispatch_days": 2,
        "bulk_rules": {
            "tiers": [{"min_pieces": 100, "percent_off": 5}, {"min_pieces": 200, "percent_off": 10}]
        },
    }
)

LEVIS_501 = Lot.model_validate(
    {
        "id": "lot-0001",
        "seller_id": "seller-01",
        "title": "Levi's 501 jeans, mixed sizes",
        "brand": "Levi's",
        "category": "jeans",
        "grade": "A",
        "listing_type": "representative",
        "pieces": 50,
        "available": 4,
        "base_price": 1350,
        "shipping": 300,
        "description": "Washed and sorted.",
    }
)


def test_two_bundles_of_501s_get_five_percent_off() -> None:
    q = quote(LEVIS_501, SELLER, bundles=2)
    assert q.pieces == 100
    assert q.percent_off == 5
    assert q.base_price == Pence(1283)  # £13.50 at 5% off is £12.825, rounded up
    assert q.shipping == Pence(300)  # shipping is never discounted
    assert q.total == Pence(158_300)  # (£12.83 + £3.00) x 100


def test_one_bundle_is_below_the_first_tier() -> None:
    q = quote(LEVIS_501, SELLER, bundles=1)
    assert (q.percent_off, q.base_price) == (0, Pence(1350))


def test_the_total_is_always_the_price_per_piece_times_pieces() -> None:
    # Rounded once per piece, then multiplied, so the total matches what the buyer sees.
    q = quote(LEVIS_501, SELLER, bundles=4)
    assert q.total == (q.base_price + q.shipping).times(q.pieces)


@pytest.mark.parametrize("bad", [0, 5, -1])
def test_you_cant_quote_for_bundles_that_dont_exist(bad: int) -> None:
    with pytest.raises(ValueError):
        quote(LEVIS_501, SELLER, bundles=bad)


def test_bundles_must_be_a_whole_number() -> None:
    with pytest.raises(TypeError):
        quote(LEVIS_501, SELLER, bundles=1.5)  # type: ignore[arg-type]


def test_a_quote_uses_only_the_lots_own_seller() -> None:
    other = SELLER.model_copy(update={"id": "seller-02"})
    with pytest.raises(ValueError):
        quote(LEVIS_501, other, bundles=2)
