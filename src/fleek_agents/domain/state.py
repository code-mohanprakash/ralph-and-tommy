"""The negotiation state machine: Fleek's Make an Offer rules as the only moves allowed.

Every change of state goes through `next_state`, which looks the move up in one table. A move
that isn't in the table, or is made by the wrong actor, is refused. So an agent can't skip a
step, accept its own offer, or approve its own deal, whatever the model decides to try.
"""

from collections.abc import Mapping
from enum import StrEnum


class NegotiationState(StrEnum):
    MATCHED = "matched"  # a buyer and a lot are paired; nothing sent yet
    OPEN = "open"  # waiting for the buyer's first offer
    OFFERED = "offered"  # the buyer's offer is on the table
    COUNTERED = "countered"  # the seller's counter-offer is on the table
    PENDING_APPROVAL = "pending_approval"  # agreed; stock locked; waiting for approval
    # endings
    CLOSED = "closed"
    WALKED_AWAY = "walked_away"
    EXPIRED = "expired"
    REJECTED_BY_HUMAN = "rejected_by_human"
    LOST_TO_OTHER_BUYER = "lost_to_other_buyer"
    NO_DEAL_POSSIBLE = "no_deal_possible"
    NEEDS_HUMAN = "needs_human"


class Move(StrEnum):
    START = "start"
    FIND_IMPOSSIBLE = "find_impossible"  # the vault says no price works for both sides
    OFFER = "offer"
    COUNTER = "counter"
    ACCEPT = "accept"  # accept the other side's card
    WALK_AWAY = "walk_away"
    EXPIRE = "expire"  # 48 hours passed with no answer
    LOSE_LOT = "lose_lot"  # another buyer's deal on this lot was accepted first
    ESCALATE = "escalate"  # hand to a person: model refusal, spend cap, repeated bad output
    APPROVE = "approve"  # by a person, or by the auto rule for small deals
    REJECT = "reject"


class Actor(StrEnum):
    BUYER_AGENT = "buyer_agent"  # Ralph
    SELLER_AGENT = "seller_agent"  # Tommy
    HUMAN = "human"  # the buyer, the seller, or a Fleek account manager
    SYSTEM = "system"  # Fleek's code: the clock, the vault, the stock lock, the auto rule


S, M, A = NegotiationState, Move, Actor
AGENTS = frozenset({A.BUYER_AGENT, A.SELLER_AGENT})
LIVE = (S.OPEN, S.OFFERED, S.COUNTERED)

# (state, move) -> (next state, who may make the move). Anything not listed is illegal.
ALLOWED: Mapping[tuple[NegotiationState, Move], tuple[NegotiationState, frozenset[Actor]]] = {
    (S.MATCHED, M.START): (S.OPEN, frozenset({A.SYSTEM})),
    (S.MATCHED, M.FIND_IMPOSSIBLE): (S.NO_DEAL_POSSIBLE, frozenset({A.SYSTEM})),
    (S.OPEN, M.OFFER): (S.OFFERED, frozenset({A.BUYER_AGENT})),
    (S.COUNTERED, M.OFFER): (S.OFFERED, frozenset({A.BUYER_AGENT})),
    (S.OFFERED, M.COUNTER): (S.COUNTERED, frozenset({A.SELLER_AGENT})),
    (S.OFFERED, M.ACCEPT): (S.PENDING_APPROVAL, frozenset({A.SELLER_AGENT})),
    (S.COUNTERED, M.ACCEPT): (S.PENDING_APPROVAL, frozenset({A.BUYER_AGENT})),
    # Offers are binding: a side can't walk away while its own card is on the table, because the
    # other side may still accept it. Otherwise a bot could offer, read the reply, and leave.
    (S.OPEN, M.WALK_AWAY): (S.WALKED_AWAY, AGENTS),
    (S.OFFERED, M.WALK_AWAY): (S.WALKED_AWAY, frozenset({A.SELLER_AGENT})),
    (S.COUNTERED, M.WALK_AWAY): (S.WALKED_AWAY, frozenset({A.BUYER_AGENT})),
    **{(state, M.LOSE_LOT): (S.LOST_TO_OTHER_BUYER, frozenset({A.SYSTEM})) for state in LIVE},
    **{(state, M.ESCALATE): (S.NEEDS_HUMAN, frozenset({A.SYSTEM})) for state in LIVE},
    **{
        (state, M.EXPIRE): (S.EXPIRED, frozenset({A.SYSTEM}))
        for state in (*LIVE, S.PENDING_APPROVAL)
    },
    (S.PENDING_APPROVAL, M.APPROVE): (S.CLOSED, frozenset({A.HUMAN, A.SYSTEM})),
    (S.PENDING_APPROVAL, M.REJECT): (S.REJECTED_BY_HUMAN, frozenset({A.HUMAN})),
}

# A state with no move out of it is an ending.
FINAL_STATES = frozenset(set(NegotiationState) - {state for state, _ in ALLOWED})


class IllegalMove(Exception):
    """A move the rules don't allow from this state, or by this actor."""


def next_state(state: NegotiationState, move: Move, *, by: Actor) -> NegotiationState:
    """The state after `move`, or IllegalMove if the rules don't allow it."""
    rule = ALLOWED.get((state, move))
    if rule is None:
        raise IllegalMove(f"Can't {move} when the negotiation is {state}")
    target, allowed_actors = rule
    if by not in allowed_actors:
        raise IllegalMove(f"{by} can't {move} when the negotiation is {state}")
    return target
