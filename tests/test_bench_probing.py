from typer.testing import CliRunner

from fleek_agents.bench.probing import (
    binary_search,
    gated,
    matches_lost,
    open_vault,
    probe_report,
)
from fleek_agents.bench.scenarios import generate
from fleek_agents.cli import app
from fleek_agents.config import MatchGateRules, PrivacyRules
from fleek_agents.vault.gate import MatchGate

GATE = MatchGateRules(on=True, answers_per_lot_per_day=20, grid_pct=5)
OFF = PrivacyRules()


def test_open_matching_gives_a_floor_away_to_the_penny_in_about_a_dozen_accounts() -> None:
    open_row, _ = probe_report(GATE, OFF, lots=40)
    assert open_row.within.value >= 0.95
    assert open_row.median_error_pct < 0.5
    assert open_row.median_questions <= 14


def test_through_the_gate_the_attacker_only_learns_the_grid_step() -> None:
    open_row, gated_row = probe_report(GATE, OFF, lots=40)
    assert gated_row.within.value < 0.7 * open_row.within.value
    assert gated_row.median_error_pct > 1.0


def test_refusals_are_read_as_no_so_a_spent_budget_misleads_the_attacker() -> None:
    tight = MatchGateRules(on=True, answers_per_lot_per_day=1, grid_pct=1)
    for s in generate(10):
        gate = MatchGate(tight, OFF)
        probe = binary_search(s, gated(s, gate), gate=gate, days=2)
        assert probe.questions > 2 and gate.refused > 0
        exact = binary_search(s, open_vault(s))
        assert abs(exact.guess.value - s.truth.seller_min.value) <= 2


def test_a_small_budget_turns_real_buyers_away_on_a_busy_market() -> None:
    # The finding that set the budget: on the seeded market many buyers ask about the same
    # lots, so 5 answers a lot a day refuses real matches: 30% with 200 buyers, 50% with 500.
    # It grows with traffic. 20 a day refuses almost none; the grid does the hiding.
    tight = matches_lost(MatchGateRules(on=True, answers_per_lot_per_day=5), OFF, wants=200)
    roomy = matches_lost(GATE, OFF, wants=200)
    assert tight.value > 0.25
    assert roomy.value < 0.07


def test_the_leak_command_attacks_matching() -> None:
    result = CliRunner().invoke(app, ["leak", "--route", "matching"])
    assert result.exit_code == 0, result.output
    assert "Matches lost: real buyers' matches the gate drops" in result.output
    assert "Open matching" in result.output and "100% (96% to" in result.output
