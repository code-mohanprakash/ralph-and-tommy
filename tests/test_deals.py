import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from fleek_agents.domain.offers import OfferCard
from fleek_agents.domain.replay import replay
from fleek_agents.domain.state import Actor, IllegalMove, Move, NegotiationState
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.deals import AcceptOutcome, accept, put_on_sale, stock_left
from fleek_agents.store.events import EventLog

S, M, A = NegotiationState, Move, Actor
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
LOT = "lot-0001"


def card(negotiation_id: str, role: str, bundles: int = 1) -> OfferCard:
    return OfferCard.model_validate(
        {
            "negotiation_id": negotiation_id,
            "round": 1,
            "from_role": role,
            "base_price": 1200,
            "bundles": bundles,
            "prepaid": False,
            "ship_by": "2026-11-20",
            "expires_at": (T0 + timedelta(hours=48)).isoformat(),
        }
    )


def countered(log: EventLog, negotiation_id: str, bundles: int = 1) -> None:
    """Bring a negotiation to the point where the buyer can accept the seller's counter."""
    log.append(negotiation_id, M.START, by=A.SYSTEM, at=T0)
    log.append(
        negotiation_id,
        M.OFFER,
        by=A.BUYER_AGENT,
        at=T0,
        card=card(negotiation_id, "buyer", bundles),
    )
    log.append(
        negotiation_id,
        M.COUNTER,
        by=A.SELLER_AGENT,
        at=T0,
        card=card(negotiation_id, "seller", bundles),
    )


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    engine = make_engine(f"sqlite:///{tmp_path / 'deals.db'}")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def log(engine: Engine) -> Iterator[EventLog]:
    with Session(engine) as session:
        yield EventLog(session)


def test_the_first_accept_wins_and_the_rivals_lose_the_lot(log: EventLog) -> None:
    put_on_sale(log.session, LOT, bundles=1)
    for n in ("neg-0001", "neg-0002", "neg-0003"):
        countered(log, n)
    log.append("neg-0003", M.WALK_AWAY, by=A.BUYER_AGENT, at=T0)  # already over

    outcome = accept(
        log, "neg-0001", lot_id=LOT, by=A.BUYER_AGENT, at=T0, rivals=["neg-0002", "neg-0003"]
    )

    assert outcome is AcceptOutcome.WON
    assert log.state("neg-0001") is S.PENDING_APPROVAL
    assert log.state("neg-0002") is S.LOST_TO_OTHER_BUYER  # told the lot is gone
    assert log.state("neg-0003") is S.WALKED_AWAY  # an ended negotiation is left alone
    assert stock_left(log.session, LOT) == 0


def test_accepting_a_lot_that_has_gone_is_told_sold(log: EventLog) -> None:
    put_on_sale(log.session, LOT, bundles=1)
    countered(log, "neg-0001")
    countered(log, "neg-0002")
    accept(log, "neg-0001", lot_id=LOT, by=A.BUYER_AGENT, at=T0)  # no rivals passed in

    outcome = accept(log, "neg-0002", lot_id=LOT, by=A.BUYER_AGENT, at=T0)

    assert outcome is AcceptOutcome.SOLD_OUT
    assert log.state("neg-0002") is S.LOST_TO_OTHER_BUYER
    assert stock_left(log.session, LOT) == 0


def test_accepting_just_after_losing_the_lot_is_told_sold_not_an_error(log: EventLog) -> None:
    # The timing that the 10-buyer race hit once: the winner has already marked this
    # negotiation lost before its buyer's accept reads the state.
    put_on_sale(log.session, LOT, bundles=1)
    countered(log, "neg-0001")
    countered(log, "neg-0002")
    accept(log, "neg-0001", lot_id=LOT, by=A.BUYER_AGENT, at=T0, rivals=["neg-0002"])
    assert log.state("neg-0002") is S.LOST_TO_OTHER_BUYER

    outcome = accept(log, "neg-0002", lot_id=LOT, by=A.BUYER_AGENT, at=T0)

    assert outcome is AcceptOutcome.SOLD_OUT
    assert len(log.read("neg-0002")) == 4  # no extra event


def test_a_pool_lot_stays_open_while_bundles_are_left(log: EventLog) -> None:
    put_on_sale(log.session, LOT, bundles=3)
    countered(log, "neg-0001", bundles=2)
    countered(log, "neg-0002", bundles=1)
    accept(log, "neg-0001", lot_id=LOT, by=A.BUYER_AGENT, at=T0, rivals=["neg-0002"])
    assert stock_left(log.session, LOT) == 1
    assert log.state("neg-0002") is S.COUNTERED  # still in the game


@pytest.mark.parametrize(
    ("setup", "actor"),
    [
        ("open", A.BUYER_AGENT),  # nothing on the table to accept
        ("offered", A.BUYER_AGENT),  # the buyer can't accept their own offer
    ],
)
def test_an_illegal_accept_takes_no_stock(log: EventLog, setup: str, actor: Actor) -> None:
    put_on_sale(log.session, LOT, bundles=1)
    log.append("neg-0001", M.START, by=A.SYSTEM, at=T0)
    if setup == "offered":
        log.append("neg-0001", M.OFFER, by=A.BUYER_AGENT, at=T0, card=card("neg-0001", "buyer"))
    before = log.saved("neg-0001")
    with pytest.raises(IllegalMove):
        accept(log, "neg-0001", lot_id=LOT, by=actor, at=T0)
    assert stock_left(log.session, LOT) == 1
    assert log.saved("neg-0001") == before


def test_ten_buyers_accepting_at_once_exactly_one_wins(engine: Engine) -> None:
    buyers = [f"neg-{n:04d}" for n in range(10)]
    with Session(engine) as session:
        put_on_sale(session, LOT, bundles=1)
        for n in buyers:
            countered(EventLog(session), n)

    outcomes: dict[str, AcceptOutcome] = {}
    errors: list[BaseException] = []
    start = threading.Barrier(len(buyers))

    def buyer(negotiation_id: str) -> None:
        try:
            with Session(engine) as session:
                log = EventLog(session)
                start.wait()  # everyone accepts at the same moment
                rivals = [n for n in buyers if n != negotiation_id]
                outcomes[negotiation_id] = accept(
                    log, negotiation_id, lot_id=LOT, by=A.BUYER_AGENT, at=T0, rivals=rivals
                )
        except BaseException as error:  # report every failure from the thread
            errors.append(error)

    threads = [threading.Thread(target=buyer, args=(n,)) for n in buyers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert sorted(outcomes.values()).count(AcceptOutcome.WON) == 1
    with Session(engine) as session:
        log = EventLog(session)
        assert stock_left(session, LOT) == 0
        states = [log.state(n) for n in buyers]
        assert states.count(S.PENDING_APPROVAL) == 1
        assert states.count(S.LOST_TO_OTHER_BUYER) == 9
        for n in buyers:
            assert log.saved(n) == replay(n, log.read(n))
