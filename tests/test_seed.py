from collections import Counter

from fleek_agents.domain.models import ListingType
from fleek_agents.market.seed import generate_market

MARKET = generate_market(seed=2026)


def test_the_market_has_the_planned_size() -> None:
    assert len(MARKET.buyers) == 500
    assert len(MARKET.sellers) == 50
    assert 1300 <= len(MARKET.lots) <= 1700
    assert len(MARKET.wants) == 500  # one want per buyer


def test_the_same_seed_gives_identical_data() -> None:
    assert generate_market(seed=2026) == MARKET


def test_a_different_seed_gives_different_data() -> None:
    assert generate_market(seed=7) != MARKET


def test_ids_are_unique_and_every_reference_resolves() -> None:
    sellers = {s.id for s in MARKET.sellers}
    buyers = {b.id for b in MARKET.buyers}
    lot_ids = [lot.id for lot in MARKET.lots]
    assert len(lot_ids) == len(set(lot_ids))
    assert all(lot.seller_id in sellers for lot in MARKET.lots)
    assert {w.buyer_id for w in MARKET.wants} == buyers


def test_it_looks_like_fleek() -> None:
    # Most lots have one available (our 44-listing sample); most supply is from Pakistan.
    one_of_one = sum(lot.available == 1 for lot in MARKET.lots) / len(MARKET.lots)
    assert one_of_one > 0.6
    assert all(
        (lot.listing_type is ListingType.EXACT) == (lot.available == 1) for lot in MARKET.lots
    )
    countries = Counter(s.country for s in MARKET.sellers)
    assert countries.most_common(1)[0][0] == "PK"
    # Shipping is a big share of the delivered price (20-45%, up to ~58%, in our sample).
    for lot in MARKET.lots:
        share = lot.shipping.value / lot.listed_price.value
        assert 0.10 <= share <= 0.60, lot.id


def test_every_seller_s_bulk_tiers_are_within_fleeks_range() -> None:
    for s in MARKET.sellers:
        assert all(0 < t.percent_off <= 15 for t in s.bulk_rules.tiers)
