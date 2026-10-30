from collections import Counter

from fleek_agents.domain.models import ListingType
from fleek_agents.domain.rules import quote
from fleek_agents.market.seed import generate_market
from fleek_agents.vault.checks import deal_possible
from fleek_agents.vault.seed import generate_mandates

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


def test_mandates_are_the_same_every_time_and_cover_everyone() -> None:
    first, again = generate_mandates(MARKET, seed=2026), generate_mandates(MARKET, seed=2026)
    assert set(first.buyers) == {b.id for b in MARKET.buyers}
    assert set(first.lots) == {lot.id for lot in MARKET.lots}
    assert all(
        first.lots[i].floor_per_piece.reveal() == again.lots[i].floor_per_piece.reveal()
        for i in first.lots
    )


def test_some_pairs_can_deal_and_some_cant() -> None:
    # A market where everything (or nothing) can close would make a dull demo and hide bugs.
    secrets = generate_mandates(MARKET, seed=2026)
    sellers = {s.id: s for s in MARKET.sellers}
    results: Counter[bool] = Counter()
    for want, lot in zip(MARKET.wants[:200], MARKET.lots[:200], strict=True):
        q = quote(lot, sellers[lot.seller_id], bundles=1)
        results[deal_possible(secrets.buyers[want.buyer_id], secrets.lots[lot.id], q)] += 1
    assert results[True] > 20 and results[False] > 20


def test_floors_sit_below_what_the_seller_would_net_at_the_listed_price() -> None:
    secrets = generate_mandates(MARKET, seed=2026)
    for lot in MARKET.lots:
        net_at_list = lot.base_price.value * 85 / 100
        assert secrets.lots[lot.id].floor_per_piece.reveal().value <= net_at_list


def test_every_buyer_has_a_budget_for_what_they_want() -> None:
    secrets = generate_mandates(MARKET, seed=2026)
    for want in MARKET.wants:
        mandate = secrets.buyers[want.buyer_id]
        assert mandate.budget is not None
        assert mandate.budget.reveal() == mandate.max_per_piece.reveal().times(want.pieces)
