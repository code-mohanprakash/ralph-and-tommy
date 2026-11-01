"""Where bench deals are lost, and the pass mark: 99% of deals that work close with the margin on.

The pass mark was written down before measuring (prep tasks/pr-plan.md, PR 78).
"""

from fleek_agents.agents.base import Agent
from fleek_agents.bench.episode import TapClient
from fleek_agents.bench.lost import LostDeals, lost_deals
from fleek_agents.bench.run import run_suite
from fleek_agents.bench.scenarios import Scenario, generate
from fleek_agents.bench.tradeoff import settings_for
from fleek_agents.config import Settings
from fleek_agents.scripted import HoldingRalph, ScriptedRalph, ScriptedTommy

SCENARIOS = generate(200)


def lost(ralph: type[ScriptedRalph], margin: int) -> LostDeals:
    settings = settings_for(Settings(), margin, 0)

    def pair(_s: Scenario, _r: int) -> tuple[Agent, Agent, list[TapClient]]:
        return ralph(), ScriptedTommy(), []

    return lost_deals(run_suite(SCENARIOS, pair, settings), settings)


def test_with_the_secret_margin_on_99_percent_of_deals_that_work_close() -> None:
    result = lost(ScriptedRalph, margin=8)
    assert result.closed / result.works >= 0.99
    assert result.haggling == 0  # every deal still lost is lost to the hidden floor
    assert result.closed + result.hidden_floor == result.works


def test_with_no_margin_every_deal_that_works_closes() -> None:
    result = lost(ScriptedRalph, margin=0)
    assert result.closed == result.works and result.hidden_floor == 0


def test_a_buyer_who_holds_loses_deals_in_the_haggling_not_to_the_floor() -> None:
    result = lost(HoldingRalph, margin=8)
    assert result.haggling > result.hidden_floor > 0  # most of the old losses were the haggling
