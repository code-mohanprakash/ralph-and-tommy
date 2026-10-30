"""Rules that must hold for any input. Hypothesis generates the inputs and shrinks failures."""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from random import Random

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.orm import Session

from fleek_agents.config import BandThresholds
from fleek_agents.domain.fees import buyer_pays, seller_receives
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import OfferCard
from fleek_agents.domain.rules import Quote
from fleek_agents.domain.state import Actor, Move, NegotiationState
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.deals import AcceptOutcome, accept, put_on_sale, stock_left
from fleek_agents.store.events import EventLog
from fleek_agents.vault.bands import Band, buyer_band, seller_band
from fleek_agents.vault.checks import can_accept, deal_possible
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate
from fleek_agents.vault.secret import SecretMoney

MANY = settings(max_examples=10_000, deadline=None)
pence = st.integers(min_value=0, max_value=50_000)  # up to £500 a piece
pieces = st.integers(min_value=1, max_value=500)
percents = st.integers(min_value=0, max_value=100)
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
ORDER = list(Band)  # strong, acceptable, stretch, outside: best to worst


def half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def independent_buyer_total(base: int, ship: int, n: int) -> int:
    """Fleek's buyer total, worked out again here without the fees module."""
    goods = (base + ship) * n
    return goods + min(half_up(Decimal(goods) * 2 / 100), 2000)


def independent_seller_net(base: int, n: int) -> int:
    gross = base * n
    return gross - half_up(Decimal(gross) * 15 / 100)


def buyer(max_: int) -> BuyerMandate:
    return BuyerMandate(buyer_id="buyer-0001", max_per_piece=SecretMoney(Pence(max_)))


def seller(floor: int) -> SellerMandate:
    return SellerMandate(seller_id="seller-01", floor_per_piece=SecretMoney(Pence(floor)))


@MANY
@given(price=pence, ship=pence, n=pieces)
def test_fees_match_an_independent_calculation_to_the_penny(price: int, ship: int, n: int) -> None:
    # The sharp version: a limit check only notices a wrong fee if a limit happens to sit
    # within a penny of the total, which random inputs almost never hit.
    assert buyer_pays(base_price=Pence(price), shipping=Pence(ship), pieces=n).total == Pence(
        independent_buyer_total(price, ship, n)
    )
    assert seller_receives(base_price=Pence(price), pieces=n).net == Pence(
        independent_seller_net(price, n)
    )


@MANY
@given(price=pence, ship=pence, n=pieces, max_=pence, floor=pence)
def test_an_accepted_price_is_never_outside_either_limit(
    price: int, ship: int, n: int, max_: int, floor: int
) -> None:
    ok = can_accept(
        buyer(max_), seller(floor), base_price=Pence(price), shipping=Pence(ship), pieces=n
    )
    inside = (
        independent_buyer_total(price, ship, n) <= max_ * n
        and independent_seller_net(price, n) >= floor * n
    )
    assert ok is inside


@MANY
@given(low=pence, extra=st.integers(1, 5000), ship=pence, n=pieces, max_=pence)
def test_a_higher_price_never_gives_the_buyer_a_better_band(
    low: int, extra: int, ship: int, n: int, max_: int
) -> None:
    t, b = BandThresholds(), buyer(max_)
    cheap = buyer_band(b, base_price=Pence(low), shipping=Pence(ship), pieces=n, t=t)
    dear = buyer_band(b, base_price=Pence(low + extra), shipping=Pence(ship), pieces=n, t=t)
    assert ORDER.index(dear) >= ORDER.index(cheap)


@MANY
@given(low=pence, extra=st.integers(1, 5000), n=pieces, floor=pence)
def test_a_lower_price_never_gives_the_seller_a_better_band(
    low: int, extra: int, n: int, floor: int
) -> None:
    t, s = BandThresholds(), seller(floor)
    cheap = seller_band(s, base_price=Pence(low), pieces=n, t=t)
    dear = seller_band(s, base_price=Pence(low + extra), pieces=n, t=t)
    assert ORDER.index(cheap) >= ORDER.index(dear)


@MANY
@given(amount=pence, pct=percents)
def test_discounts_and_shares_stay_between_zero_and_the_amount(amount: int, pct: int) -> None:
    for result in (Pence(amount).percent(pct), Pence(amount).discounted(pct)):
        assert Pence(0) <= result <= Pence(amount)
    # a discount and the share it removes add back up to within a penny
    assert abs(Pence(amount).discounted(pct).value + Pence(amount).percent(pct).value - amount) <= 1


@settings(max_examples=2_000, deadline=None)
@given(
    base=st.integers(0, 3000),
    ship=st.integers(0, 600),
    n=st.integers(1, 60),
    max_=st.integers(0, 4000),
    floor=st.integers(0, 3000),
)
def test_deal_possible_means_some_price_really_works(
    base: int, ship: int, n: int, max_: int, floor: int
) -> None:
    q = Quote(
        lot_id="lot-0001",
        bundles=1,
        pieces=n,
        percent_off=0,
        base_price=Pence(base),
        shipping=Pence(ship),
        total=(Pence(base) + Pence(ship)).times(n),
    )
    works = [
        p
        for p in range(base + 1)
        if independent_buyer_total(p, ship, n) <= max_ * n
        and independent_seller_net(p, n) >= floor * n
    ]
    assert deal_possible(buyer(max_), seller(floor), q) is bool(works)


@settings(max_examples=300, deadline=None)
@given(
    stock=st.integers(1, 5),
    asks=st.lists(st.integers(1, 3), min_size=1, max_size=8),
    order=st.randoms(use_true_random=False),
)
def test_stock_is_never_oversold(stock: int, asks: list[int], order: Random) -> None:
    engine = make_engine("sqlite://")  # a fresh in-memory database per example
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        log = EventLog(session)
        put_on_sale(session, "lot-0001", bundles=stock)
        ids = [f"neg-{n:04d}" for n in range(len(asks))]
        for negotiation_id, bundles in zip(ids, asks, strict=True):
            _bring_to_counter(log, negotiation_id, bundles)
        won = 0
        for i in order.sample(range(len(ids)), len(ids)):
            outcome = accept(
                log, ids[i], lot_id="lot-0001", by=Actor.BUYER_AGENT, at=T0, rivals=ids
            )
            if outcome is AcceptOutcome.WON:
                won += asks[i]
            else:
                assert log.state(ids[i]) is NegotiationState.LOST_TO_OTHER_BUYER
        assert won <= stock
        assert stock_left(session, "lot-0001") == stock - won


def _bring_to_counter(log: EventLog, negotiation_id: str, bundles: int) -> None:
    def card(role: str) -> OfferCard:
        return OfferCard.model_validate(
            {
                "negotiation_id": negotiation_id,
                "round": 1,
                "from_role": role,
                "base_price": 1000,
                "bundles": bundles,
                "prepaid": False,
                "ship_by": "2026-11-20",
                "expires_at": "2026-11-04T09:00:00Z",
            }
        )

    log.append(negotiation_id, Move.START, by=Actor.SYSTEM, at=T0)
    log.append(negotiation_id, Move.OFFER, by=Actor.BUYER_AGENT, at=T0, card=card("buyer"))
    log.append(negotiation_id, Move.COUNTER, by=Actor.SELLER_AGENT, at=T0, card=card("seller"))
