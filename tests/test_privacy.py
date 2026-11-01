import pytest

from fleek_agents.agents.scripted import BoulwareTommy, ScriptedRalph, ScriptedTommy
from fleek_agents.bench.episode import TapClient
from fleek_agents.bench.moves import (
    probe_sessions,
)
from fleek_agents.bench.run import run_suite
from fleek_agents.bench.scenarios import PIECES, Scenario, generate
from fleek_agents.bench.score import breach
from fleek_agents.config import PrivacyRules, Settings
from fleek_agents.domain.money import Pence
from fleek_agents.vault.mandate import SellerMandate
from fleek_agents.vault.privacy import guarded, jitter, lowest_allowed

ON = PrivacyRules(on=True, margin_max_pct=8, noise_pct=4)
NOISY = Settings(privacy=ON)


def floor_of(limit: SellerMandate) -> int:
    return limit.floor_per_piece.reveal().value


def test_the_margin_only_ever_raises_a_floor_and_by_at_most_the_setting() -> None:
    raised = 0
    for s in generate(100):
        real, worked_to = floor_of(s.seller_limit), floor_of(guarded(s.seller_limit, ON))
        assert real <= worked_to <= real + -(-real * 8 // 100)
        raised += worked_to > real
    assert raised > 90  # almost every lot gets some margin


def test_a_lot_keeps_its_margin_across_negotiations_but_not_across_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit = generate(1)[0].seller_limit
    first, again = floor_of(guarded(limit, ON)), floor_of(guarded(limit, ON))
    assert first == again  # a patient attacker can't average it away
    monkeypatch.setenv("FLEEK_VAULT_KEY", "a-different-key")
    margins = {floor_of(guarded(s.seller_limit, ON)) for s in generate(20)}
    monkeypatch.delenv("FLEEK_VAULT_KEY")
    ours = {floor_of(guarded(s.seller_limit, ON)) for s in generate(20)}
    assert margins != ours


def test_with_the_layer_off_nothing_changes() -> None:
    limit = generate(1)[0].seller_limit
    assert guarded(limit, PrivacyRules()) is limit
    price = Pence(1200)
    same = jitter(
        price,
        limit=limit,
        previous=Pence(1300),
        list_price=Pence(1400),
        pieces=PIECES,
        lot_id="lot-1",
        card_id="x",
        rounds_left=4,
        max_rounds=6,
        rules=PrivacyRules(),
    )
    assert same == price


def _jitters(scenario: Scenario, price: int, previous: int, n: int) -> list[Pence]:
    limit = guarded(scenario.seller_limit, ON)
    return [
        jitter(
            Pence(price),
            limit=limit,
            previous=Pence(previous),
            list_price=scenario.lot.base_price,
            pieces=PIECES,
            lot_id=scenario.lot.id,
            card_id=f"neg-{i}",
            rounds_left=5,
            max_rounds=6,
            rules=PrivacyRules(on=True, margin_max_pct=8, noise_pct=20),
        )
        for i in range(n)
    ]


def test_with_the_layer_on_no_deal_breaks_a_real_limit_and_no_card_goes_below_a_floor() -> None:
    for tommy in (ScriptedTommy, BoulwareTommy):

        def pair(
            _s: Scenario, _r: int, tommy: type[ScriptedTommy] = tommy
        ) -> tuple[ScriptedRalph, ScriptedTommy, list[TapClient]]:
            return ScriptedRalph(), tommy(), []

        episodes = run_suite(generate(100), pair, NOISY)
        assert not any(breach(e) for e in episodes)
        for e in episodes:
            worked_to = guarded(e.scenario.seller_limit, ON)
            low = lowest_allowed(worked_to, PIECES, e.scenario.lot.base_price)
            assert all(c >= low for c in e.counters)


def test_boulware_tommy_holds_firmer_early_and_never_passes_his_floor() -> None:
    settings = Settings()
    firmer = 0
    for s in generate(30):
        thirds = probe_sessions(s, lambda _s: (ScriptedTommy(), []), settings, 1)[0]
        holder = probe_sessions(s, lambda _s: (BoulwareTommy(), []), settings, 1)[0]
        # Compare only where thirds-Tommy moved: if his bigger step would have crossed his
        # floor he holds, and a small Boulware step can still fit under it.
        moved = len(thirds.counters) > 1 and thirds.counters[1] < thirds.counters[0]
        if moved and len(holder.counters) > 1:
            assert holder.counters[1] >= thirds.counters[1]
            firmer += holder.counters[1] > thirds.counters[1]
        assert all(c >= s.truth.seller_min for c in holder.counters)
    assert firmer > 10
