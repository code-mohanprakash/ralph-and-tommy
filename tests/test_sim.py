from fleek_agents.agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.domain.state import NegotiationState
from fleek_agents.evals.sim import simulate
from fleek_agents.market.seed import generate_market
from fleek_agents.vault.seed import generate_mandates

MARKET = generate_market(seed=2026)
SECRETS = generate_mandates(MARKET, seed=2026)
BUYERS = [w.buyer_id for w in MARKET.wants[:100]]


def test_a_scripted_simulation_measures_every_buyer() -> None:
    summary = simulate(
        MARKET, SECRETS, BUYERS, agents="scripted", ralph=ScriptedRalph, tommy=ScriptedTommy
    )
    assert len(summary.results) == 100
    assert summary.deals  # some deals close
    for r in summary.deals:
        assert r.buyer_gain >= 0 and r.seller_gain >= 0  # every deal inside both limits
    line = summary.line()
    assert line["buyers"] == "100" and line["AI cost per deal"] == "0"


def test_buyers_can_lose_a_lot_to_someone_faster() -> None:
    summary = simulate(
        MARKET, SECRETS, BUYERS, agents="scripted", ralph=ScriptedRalph, tommy=ScriptedTommy
    )
    states = {r.state for r in summary.results}
    assert NegotiationState.LOST_TO_OTHER_BUYER in states  # one-of-one lots, shared by buyers


def test_the_recorded_haiku_run_replays_with_the_same_results() -> None:
    from typer.testing import CliRunner

    from fleek_agents.cli import app

    result = CliRunner().invoke(
        app, ["simulate", "--agents", "claude-haiku-5-5", "--buyers", "30"], env={"COLUMNS": "250"}
    )
    assert result.exit_code == 0, result.output
    assert "21 (70%)" in result.output and "11.6%" in result.output and "0.74¢" in result.output


def test_the_recorded_sonnet_run_replays_with_the_same_results() -> None:
    from typer.testing import CliRunner

    from fleek_agents.cli import app

    result = CliRunner().invoke(
        app, ["simulate", "--agents", "claude-sonnet-5-5", "--buyers", "10"], env={"COLUMNS": "250"}
    )
    assert result.exit_code == 0, result.output
    assert "9 (90%)" in result.output and "11.0%" in result.output and "7.70¢" in result.output
