import pytest
from pydantic import ValidationError

from fleek_agents.domain.models import BulkRules, BulkTier, Seller


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
