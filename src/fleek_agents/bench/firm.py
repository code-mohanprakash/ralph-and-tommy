"""Firm mode against haggling: deals kept, Fleek's commission, and whether the floor shows.

For each lot the seller either haggles (Tommy gives ground towards the secret floor) or sells at
a public firm price. The firm price here follows one rule for every lot (a fixed share of the
list price), so it can't carry anything about the floor. A lot whose floor is above that price
can't use it: the vault refuses, and the seller would have to pick a higher one.

"Floor shows" is measured directly, not estimated: each lot is negotiated twice with two
different floors and everything else the same. If the two runs differ anywhere a buyer can see
(a card, a move, a time), the floor changed what the buyer saw.
"""

from dataclasses import dataclass, replace

from fleek_agents.agents.base import Agent
from fleek_agents.bench.episode import Episode, TapClient, run_episode
from fleek_agents.bench.scenarios import Scenario, generate
from fleek_agents.bench.stats import Estimate, cluster_mean
from fleek_agents.config import Settings
from fleek_agents.domain.fees import COMMISSION_PCT
from fleek_agents.domain.models import Lot, SellMode
from fleek_agents.domain.money import Pence
from fleek_agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.vault.mandate import SellerMandate
from fleek_agents.vault.secret import SecretMoney

FIRM_SHARES = (80, 85, 90)  # firm price as a % of list
OTHER_FLOOR_PCT = 90  # the second run's floor, as a % of the first


@dataclass(frozen=True)
class ModeRow:
    label: str
    lots: int  # lots that can use this mode
    deals: Estimate  # agreed, out of the lots where a deal was possible
    commission_vs_haggle: float  # Fleek's 15% on these lots, as a share of haggling on them
    floor_shows: int  # lots where a different floor changed what the buyer saw


def _pair(_scenario: Scenario, _run: int) -> tuple[Agent, Agent, list[TapClient]]:
    return ScriptedRalph(), ScriptedTommy(), []


def firm_lot(lot: Lot, share_pct: int) -> Lot:
    price = lot.base_price.value * share_pct // 100 // 5 * 5
    return Lot.model_validate(lot.model_dump() | {"sell_mode": SellMode.FIRM, "firm_price": price})


def _other_floor(limit: SellerMandate) -> SellerMandate:
    floor = limit.floor_per_piece.reveal().value
    return replace(limit, floor_per_piece=SecretMoney(Pence(floor * OTHER_FLOOR_PCT // 100)))


@dataclass(frozen=True)
class _Lot:
    episode: Episode
    floor_shows: bool

    @property
    def commission(self) -> int:
        e = self.episode
        if not e.agreed or e.price is None:
            return 0
        return e.price.times(e.scenario.lot.pieces).percent(COMMISSION_PCT).value


def _run(scenario: Scenario, settings: Settings) -> _Lot:
    first = run_episode(scenario, _pair, settings)
    other = replace(scenario, seller_limit=_other_floor(scenario.seller_limit))
    second = run_episode(other, _pair, settings)
    return _Lot(first, (first.state, first.cards) != (second.state, second.cards))


def _row(label: str, runs: dict[str, _Lot], haggled: dict[str, _Lot]) -> ModeRow:
    workable = [r.episode for r in runs.values() if r.episode.scenario.truth.deal_possible]
    base = sum(haggled[key].commission for key in runs)
    return ModeRow(
        label,
        len(runs),
        cluster_mean([(e.scenario.key, float(e.agreed)) for e in workable]),
        sum(r.commission for r in runs.values()) / base if base else 0.0,
        sum(r.floor_shows for r in runs.values()),
    )


def firm_report(settings: Settings, *, count: int = 200) -> list[ModeRow]:
    """Haggle, then firm at each share of list. Scripted agents: same answers every run."""
    scenarios = generate(count)
    haggled = {s.key: _run(s, settings) for s in scenarios}
    rows = [_row("haggle", haggled, haggled)]
    for share in FIRM_SHARES:
        runs = {}
        for s in scenarios:
            lot = firm_lot(s.lot, share)
            if lot.firm_price is not None and lot.firm_price >= s.truth.seller_min:
                runs[s.key] = _run(replace(s, lot=lot), settings)
        rows.append(_row(f"firm at {share}% of list", runs, haggled))
    return rows
