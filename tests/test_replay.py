from datetime import UTC, datetime, timedelta

import pytest

from fleek_agents.domain.events import Event
from fleek_agents.domain.offers import OfferCard
from fleek_agents.domain.replay import Snapshot, replay
from fleek_agents.domain.state import Actor, Move, NegotiationState

S, M, A = NegotiationState, Move, Actor
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def card(role: str, price: int) -> OfferCard:
    return OfferCard.model_validate(
        {
            "negotiation_id": "neg-0001",
            "round": 1,
            "from_role": role,
            "base_price": price,
            "bundles": 1,
            "prepaid": False,
            "ship_by": "2026-11-20",
            "expires_at": (T0 + timedelta(hours=48)).isoformat(),
        }
    )


def ev(
    seq: int,
    move: Move,
    by: Actor,
    frm: NegotiationState,
    to: NegotiationState,
    c: OfferCard | None = None,
) -> Event:
    return Event(
        negotiation_id="neg-0001",
        seq=seq,
        at=T0 + timedelta(minutes=seq),
        by=by,
        move=move,
        from_state=frm,
        to_state=to,
        card=c,
    )


HISTORY = [
    ev(1, M.START, A.SYSTEM, S.MATCHED, S.OPEN),
    ev(2, M.OFFER, A.BUYER_AGENT, S.OPEN, S.OFFERED, card("buyer", 1100)),
    ev(3, M.COUNTER, A.SELLER_AGENT, S.OFFERED, S.COUNTERED, card("seller", 1300)),
    ev(4, M.OFFER, A.BUYER_AGENT, S.COUNTERED, S.OFFERED, card("buyer", 1200)),
]


def test_no_events_means_matched() -> None:
    assert replay("neg-0001", []) == Snapshot(negotiation_id="neg-0001")


def test_replay_gives_the_state_and_the_latest_card_from_each_side() -> None:
    snap = replay("neg-0001", HISTORY)
    assert snap.state is S.OFFERED
    assert snap.seq == 4
    assert snap.last_offer == card("buyer", 1200)
    assert snap.last_counter == card("seller", 1300)
    assert snap.updated_at == T0 + timedelta(minutes=4)


@pytest.mark.parametrize(
    "broken",
    [
        [HISTORY[0], HISTORY[2]],  # event 2 is missing
        [HISTORY[1]],  # doesn't start at 1
        [HISTORY[0], ev(2, M.COUNTER, A.SELLER_AGENT, S.OFFERED, S.COUNTERED, card("seller", 1))],
    ],
)
def test_a_history_with_a_gap_or_a_break_is_refused(broken: list[Event]) -> None:
    with pytest.raises(ValueError):
        replay("neg-0001", broken)


def test_events_from_another_negotiation_are_refused() -> None:
    with pytest.raises(ValueError):
        replay("neg-0002", HISTORY)
