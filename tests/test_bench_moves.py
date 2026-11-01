from dataclasses import replace

from fleek_agents.bench.moves import (
    Learned,
    consistent,
    fitting_floors,
    leave_one_out,
    moves_report,
    probe_sessions,
    scripted_tommy,
    stop_guess,
)
from fleek_agents.bench.scenarios import generate
from fleek_agents.config import Settings
from fleek_agents.domain.money import Pence

SETTINGS = Settings()


def test_the_true_floor_always_fits_what_scripted_tommy_did() -> None:
    # If the replay of Tommy's rules ever ruled out the real floor, every Bayesian number
    # would be wrong. Checked over three visits with different climbs.
    for scenario in generate(15):
        visits = probe_sessions(scenario, scripted_tommy, SETTINGS, 3)
        assert all(consistent(v, scenario.truth.floor_canary, SETTINGS) for v in visits)


def test_more_visits_never_widen_what_the_attacker_knows() -> None:
    for scenario in generate(10):
        visits = probe_sessions(scenario, scripted_tommy, SETTINGS, 3)
        one, all_three = fitting_floors(visits[:1], SETTINGS), fitting_floors(visits, SETTINGS)
        assert set(all_three) <= set(one)
        assert scenario.truth.floor_canary in all_three


def test_stopping_point_is_never_below_the_floor() -> None:
    for scenario in generate(20):
        visits = probe_sessions(scenario, scripted_tommy, SETTINGS, 1)
        assert stop_guess(visits) >= scenario.truth.seller_min


def test_leave_one_out_never_sees_the_lot_it_guesses() -> None:
    scenario = generate(1)[0]
    visit = probe_sessions(scenario, scripted_tommy, SETTINGS, 1)[0]
    truth = scenario.truth
    other = replace(truth, seller_min=Pence(truth.seller_min.value + 100))
    twin = replace(visit, scenario=replace(scenario, truth=other))
    guesses = leave_one_out([visit, twin])  # identical moves, different truths
    assert guesses[0][1] == twin.scenario.truth.seller_min  # learned only from the twin
    assert guesses[1][1] == truth.seller_min
    assert Learned([]).k == 15


def test_scripted_tommy_gives_his_floor_away_to_a_patient_attacker() -> None:
    # The "before" picture for the next PR's fix. If this stops holding, the fix's numbers
    # need re-reading.
    rows = {r.attacker: r for r in moves_report(SETTINGS)}
    assert rows["Bayesian, 3 visits"].within.value >= 0.5
    assert rows["Bayesian, 3 visits"].gain > 0.9
    assert all(r.gain > 0.5 for r in rows.values())
