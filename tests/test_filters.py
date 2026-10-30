from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from fleek_agents.domain.models import Lot, Market, Want
from fleek_agents.market.seed import generate_market
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.deals import StockRow, stock_left
from fleek_agents.store.market import hard_filter, load_market

MARKET = generate_market(seed=2026)


def by_hand(market: Market, want: Want) -> list[str]:
    """The same rules in plain Python, to check the SQL against."""

    def fits(lot: Lot) -> bool:
        return (
            lot.category == want.category
            and (not want.brands or lot.brand in want.brands)
            and lot.grade in want.grades
            and lot.available >= 1
            and lot.pieces <= want.pieces * 2
        )

    return sorted(lot.id for lot in market.lots if fits(lot))


@pytest.fixture(scope="module")
def session() -> Iterator[Session]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        load_market(session, MARKET)
        yield session


def test_loading_puts_every_lot_on_sale(session: Session) -> None:
    for lot in MARKET.lots[:50]:
        assert stock_left(session, lot.id) == lot.available


def test_sql_filters_agree_with_python_for_every_buyer(session: Session) -> None:
    for want in MARKET.wants:
        assert [lot.id for lot in hard_filter(session, want)] == by_hand(MARKET, want)


def test_a_filter_returns_whole_lots(session: Session) -> None:
    want = next(w for w in MARKET.wants if by_hand(MARKET, w))
    lots = hard_filter(session, want)
    assert all(isinstance(lot, Lot) and lot.category == want.category for lot in lots)


def test_a_sold_out_lot_is_filtered_out(session: Session) -> None:
    want = next(w for w in MARKET.wants if by_hand(MARKET, w))
    first = hard_filter(session, want)[0]
    row = session.get(StockRow, first.id)
    assert row is not None
    row.available = 0
    session.flush()
    assert first.id not in [lot.id for lot in hard_filter(session, want)]
    session.rollback()


def test_the_filters_narrow_the_market_a_lot() -> None:
    # Seed 2026: a buyer passes 62 of 1,494 lots on average (about 4%). The widest, any brand
    # and any grade in a common category, passes about one category's worth (14%).
    sizes = [len(by_hand(MARKET, w)) for w in MARKET.wants]
    assert sum(sizes) / len(sizes) < len(MARKET.lots) * 0.05
    assert max(sizes) < len(MARKET.lots) * 0.20
