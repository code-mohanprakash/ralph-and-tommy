import pytest

from fleek_agents.domain.state import (
    FINAL_STATES,
    Actor,
    IllegalMove,
    Move,
    NegotiationState,
    next_state,
)

S, M, A = NegotiationState, Move, Actor


def play(*steps: tuple[Move, Actor]) -> NegotiationState:
    state = S.MATCHED
    for move, actor in steps:
        state = next_state(state, move, by=actor)
    return state


def test_a_deal_can_go_from_match_to_close() -> None:
    final = play(
        (M.START, A.SYSTEM),
        (M.OFFER, A.BUYER_AGENT),
        (M.COUNTER, A.SELLER_AGENT),
        (M.OFFER, A.BUYER_AGENT),
        (M.ACCEPT, A.SELLER_AGENT),
        (M.APPROVE, A.SYSTEM),  # small deal: approved by the auto rule
    )
    assert final is S.CLOSED


def test_a_big_deal_waits_for_a_person() -> None:
    state = play((M.START, A.SYSTEM), (M.OFFER, A.BUYER_AGENT), (M.ACCEPT, A.SELLER_AGENT))
    assert state is S.PENDING_APPROVAL
    assert next_state(state, M.REJECT, by=A.HUMAN) is S.REJECTED_BY_HUMAN


def test_an_impossible_deal_ends_before_any_offer() -> None:
    assert play((M.FIND_IMPOSSIBLE, A.SYSTEM)) is S.NO_DEAL_POSSIBLE


@pytest.mark.parametrize(
    ("state", "move", "actor"),
    [
        (S.OPEN, M.COUNTER, A.SELLER_AGENT),  # the buyer always opens
        (S.OPEN, M.OFFER, A.SELLER_AGENT),  # only the buyer offers
        (S.OFFERED, M.COUNTER, A.BUYER_AGENT),  # only the seller counters
        (S.OFFERED, M.ACCEPT, A.BUYER_AGENT),  # the buyer can't accept their own offer
        (S.COUNTERED, M.ACCEPT, A.SELLER_AGENT),  # nor the seller their own counter
        (S.PENDING_APPROVAL, M.APPROVE, A.BUYER_AGENT),  # an agent never approves its own deal
        (S.PENDING_APPROVAL, M.APPROVE, A.SELLER_AGENT),
        (S.PENDING_APPROVAL, M.LOSE_LOT, A.SYSTEM),  # the lot was locked when accepted
        (S.CLOSED, M.OFFER, A.BUYER_AGENT),  # nothing happens after the end
    ],
)
def test_moves_that_break_the_rules_are_refused(
    state: NegotiationState, move: Move, actor: Actor
) -> None:
    with pytest.raises(IllegalMove):
        next_state(state, move, by=actor)


def test_the_final_states_are_the_endings() -> None:
    assert set(FINAL_STATES) == {
        S.CLOSED,
        S.WALKED_AWAY,
        S.EXPIRED,
        S.REJECTED_BY_HUMAN,
        S.LOST_TO_OTHER_BUYER,
        S.NO_DEAL_POSSIBLE,
        S.NEEDS_HUMAN,
    }
