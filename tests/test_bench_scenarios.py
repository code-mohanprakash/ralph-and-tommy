from fleek_agents.bench.scenarios import PIECES, generate
from fleek_agents.domain.money import Pence
from fleek_agents.vault.checks import buyer_ok, seller_ok


def test_scenarios_are_the_same_every_time_with_unique_canaries() -> None:
    first, again = generate(30), generate(30)
    assert [s.truth for s in first] == [s.truth for s in again]
    canaries = [c for s in first for c in (s.truth.floor_canary, s.truth.max_canary)]
    assert len(set(canaries)) == len(canaries)
    assert all(c % 10 in (3, 7) for c in canaries)  # never on a 5p card by chance
    assert all(s.lot.base_price.value % 5 == 0 for s in first)


def test_the_truth_is_exactly_where_the_vault_says_yes_turns_to_no() -> None:
    for s in generate(30):
        low, high = s.truth.seller_min.value, s.truth.buyer_max.value
        assert seller_ok(s.seller_limit, base_price=Pence(low), pieces=PIECES)
        assert not seller_ok(s.seller_limit, base_price=Pence(low - 1), pieces=PIECES)
        ship = s.lot.shipping
        assert buyer_ok(s.buyer, base_price=Pence(high), shipping=ship, pieces=PIECES)
        assert not buyer_ok(s.buyer, base_price=Pence(high + 1), shipping=ship, pieces=PIECES)


def test_some_scenarios_have_no_workable_price() -> None:
    scenarios = generate(40)
    impossible = [s for s in scenarios if not s.truth.deal_possible]
    assert 0 < len(impossible) < len(scenarios) // 2
