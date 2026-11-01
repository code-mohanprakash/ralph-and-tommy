from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from fleek_agents.config import MatchGateRules
from fleek_agents.domain.money import Pence
from fleek_agents.market.seed import generate_market
from fleek_agents.matching.funnel import bundles_for, possible_deals
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.market import hard_filter, load_market
from fleek_agents.vault.checks import deal_possible
from fleek_agents.vault.gate import MatchGate
from fleek_agents.vault.mandate import BuyerMandate
from fleek_agents.vault.secret import SecretMoney
from fleek_agents.vault.seed import generate_mandates

MARKET = generate_market(seed=2026)
SECRETS = generate_mandates(MARKET, seed=2026)


@pytest.fixture(scope="module")
def session() -> Iterator[Session]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        load_market(session, MARKET)
        yield session


def test_only_lots_where_some_price_works_go_through(session: Session) -> None:
    for want in MARKET.wants[:100]:
        passed = hard_filter(session, want)
        kept = possible_deals(session, MARKET, SECRETS, want)
        kept_ids = {c.lot.id for c in kept}
        assert kept_ids <= {lot.id for lot in passed}
        for c in kept:
            assert deal_possible(SECRETS.buyers[want.buyer_id], SECRETS.lots[c.lot.id], c.quote)


def test_a_pair_that_can_never_close_is_dropped(session: Session) -> None:
    want = next(w for w in MARKET.wants if possible_deals(session, MARKET, SECRETS, w))
    broke = BuyerMandate(buyer_id=want.buyer_id, max_per_piece=SecretMoney(Pence(1)))
    secrets = type(SECRETS)(buyers={**SECRETS.buyers, want.buyer_id: broke}, lots=SECRETS.lots)
    assert possible_deals(session, MARKET, secrets, want) == []


@pytest.mark.parametrize(
    ("wanted", "per_bundle", "available", "bundles"),
    [(100, 50, 4, 2), (100, 30, 4, 3), (20, 50, 1, 1), (500, 50, 4, 4), (10, 15, 3, 1)],
)
def test_bundles_come_closest_to_what_the_buyer_wants(
    wanted: int, per_bundle: int, available: int, bundles: int
) -> None:
    want = MARKET.wants[0].model_copy(update={"pieces": wanted})
    lot = MARKET.lots[0].model_copy(update={"pieces": per_bundle, "available": available})
    assert bundles_for(want, lot) == bundles


def test_the_funnel_cuts_negotiations_down(session: Session) -> None:
    filtered = possible = 0
    for want in MARKET.wants:
        filtered += len(hard_filter(session, want))
        possible += len(possible_deals(session, MARKET, SECRETS, want))
    assert 0 < possible < filtered
    print(f"\n{len(MARKET.wants) * len(MARKET.lots):,} pairs -> {filtered:,} -> {possible:,}")


def test_through_the_gate_matching_only_ever_drops_lots_never_adds_them(session: Session) -> None:
    gate = MatchGate(MatchGateRules(on=True, answers_per_lot_per_day=5, grid_pct=5))
    day = date(2026, 11, 2)
    kept_open = kept_gated = 0
    for want in MARKET.wants[:100]:
        open_ids = {c.lot.id for c in possible_deals(session, MARKET, SECRETS, want)}
        gated = possible_deals(session, MARKET, SECRETS, want, gate=gate, today=day)
        gated_ids = {c.lot.id for c in gated}
        assert gated_ids <= open_ids  # rounding down never invents a match
        kept_open, kept_gated = kept_open + len(open_ids), kept_gated + len(gated_ids)
    assert 0 < kept_gated < kept_open  # it costs some matches, measured in fleek leak


def test_the_gate_needs_to_know_the_day(session: Session) -> None:
    with pytest.raises(ValueError, match="which day"):
        possible_deals(session, MARKET, SECRETS, MARKET.wants[0], gate=MatchGate())
