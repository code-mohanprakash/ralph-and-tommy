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
        (S.OFFERED, M.WALK_AWAY, A.BUYER_AGENT),  # offers are binding: the buyer's is still open
        (S.COUNTERED, M.WALK_AWAY, A.SELLER_AGENT),  # and so is the seller's counter
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


# Written out by hand from Fleek's Make an Offer rules, separately from the table in state.py,
# so a slip in either one shows up as a difference.
H, SY, BA, SA = A.HUMAN, A.SYSTEM, A.BUYER_AGENT, A.SELLER_AGENT
EXPECTED = {
    (S.MATCHED, M.START, SY): S.OPEN,
    (S.MATCHED, M.FIND_IMPOSSIBLE, SY): S.NO_DEAL_POSSIBLE,
    (S.OPEN, M.OFFER, BA): S.OFFERED,
    (S.OPEN, M.WALK_AWAY, BA): S.WALKED_AWAY,
    (S.OPEN, M.WALK_AWAY, SA): S.WALKED_AWAY,
    (S.OPEN, M.EXPIRE, SY): S.EXPIRED,
    (S.OPEN, M.LOSE_LOT, SY): S.LOST_TO_OTHER_BUYER,
    (S.OPEN, M.ESCALATE, SY): S.NEEDS_HUMAN,
    (S.OFFERED, M.COUNTER, SA): S.COUNTERED,
    (S.OFFERED, M.ACCEPT, SA): S.PENDING_APPROVAL,
    (S.OFFERED, M.WALK_AWAY, SA): S.WALKED_AWAY,
    (S.OFFERED, M.EXPIRE, SY): S.EXPIRED,
    (S.OFFERED, M.LOSE_LOT, SY): S.LOST_TO_OTHER_BUYER,
    (S.OFFERED, M.ESCALATE, SY): S.NEEDS_HUMAN,
    (S.COUNTERED, M.OFFER, BA): S.OFFERED,
    (S.COUNTERED, M.ACCEPT, BA): S.PENDING_APPROVAL,
    (S.COUNTERED, M.WALK_AWAY, BA): S.WALKED_AWAY,
    (S.COUNTERED, M.EXPIRE, SY): S.EXPIRED,
    (S.COUNTERED, M.LOSE_LOT, SY): S.LOST_TO_OTHER_BUYER,
    (S.COUNTERED, M.ESCALATE, SY): S.NEEDS_HUMAN,
    (S.PENDING_APPROVAL, M.APPROVE, H): S.CLOSED,
    (S.PENDING_APPROVAL, M.APPROVE, SY): S.CLOSED,
    (S.PENDING_APPROVAL, M.REJECT, H): S.REJECTED_BY_HUMAN,
    (S.PENDING_APPROVAL, M.EXPIRE, SY): S.EXPIRED,
}
EVERY_MOVE = [(state, move, actor) for state in S for move in M for actor in A]


@pytest.mark.parametrize(("state", "move", "actor"), EVERY_MOVE)
def test_every_move_from_every_state_by_every_actor(
    state: NegotiationState, move: Move, actor: Actor
) -> None:
    expected = EXPECTED.get((state, move, actor))
    if expected is None:
        with pytest.raises(IllegalMove):
            next_state(state, move, by=actor)
    else:
        assert next_state(state, move, by=actor) is expected
