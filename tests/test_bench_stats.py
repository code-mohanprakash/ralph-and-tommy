from fleek_agents.bench.stats import (
    cluster_mean,
    pass_k,
    sign_test,
    wilson,
    zero_failure_bound,
)


def test_a_rate_gets_an_interval_that_contains_it_and_stays_between_0_and_1() -> None:
    half = wilson(5, 10)
    assert half.low < 0.5 < half.high
    none = wilson(0, 10)
    assert none.value == 0 and none.low == 0 and 0.2 < none.high < 0.35
    every = wilson(10, 10)
    assert every.high == 1 and every.low > 0.65


def test_zero_failures_still_has_an_upper_bound_of_about_3_over_n() -> None:
    assert abs(zero_failure_bound(100) - 0.0295) < 0.001
    assert abs(zero_failure_bound(300) - 3 / 300) < 0.001
    assert zero_failure_bound(0) == 1.0


def test_runs_of_one_scenario_count_as_one_cluster() -> None:
    # 9 runs of s1 at 1.0 and 1 run of s2 at 0.0: two scenarios, mean of means is 0.5, not 0.9.
    values = [("s1", 1.0)] * 9 + [("s2", 0.0)]
    estimate = cluster_mean(values)
    assert estimate.value == 0.5 and estimate.n == 2
    assert estimate.low <= 0.5 <= estimate.high


def test_the_interval_is_the_same_every_time() -> None:
    values = [(f"s{i}", float(i % 3 == 0)) for i in range(30)]
    assert cluster_mean(values) == cluster_mean(values)


def test_sign_test_drops_ties_and_is_exact() -> None:
    assert sign_test([1.0] * 10) == 2 / 1024  # ten ups in a row, two-sided
    assert sign_test([1.0, -1.0, 0.0, 0.0]) == 1.0
    assert sign_test([]) == 1.0


def test_pass_k_needs_every_run_of_a_scenario_to_pass() -> None:
    results = [("s1", True), ("s1", True), ("s2", True), ("s2", False)]
    assert pass_k(results).value == 0.5
