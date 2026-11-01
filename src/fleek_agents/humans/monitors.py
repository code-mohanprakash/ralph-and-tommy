"""Monitors: plain-code checks that flag a negotiation to an account manager.

The hard limits are in code and stop bad deals outright. Monitors are the next layer: they don't
block anything, they point a person at behaviour worth a look, the way labs put monitors on
their agents (and Project Vend found a second AI on the same model shares its blind spots, so
these are code, not a model). Each is scored on the bench for what it catches and how often it
cries wolf (bench/monitoring.py).

- big_drop: a seller's counter fell by more than 15% of the list price in one round. Tommy's
  rules never do that; an agent that does may be malfunctioning or manipulated.
- probing: a buyer climbed in small binding steps and walked away without accepting, the
  pattern of an attacker mapping a floor (bench/moves.py).
- returning: the same buyer came back to the same lot after failing, more than once.
- gate_refusals: the match gate refused questions about a lot today (vault/gate.py).

Nothing here reads the vault: monitors see what an account manager could see.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import OfferCard

BIG_DROP_PCT = 15
SMALL_STEP_PCT = 8
PROBING_OFFERS = 3
RETURNS = 2


class Flag(StrEnum):
    BIG_DROP = "big_drop"
    PROBING = "probing"
    RETURNING = "returning"
    GATE_REFUSALS = "gate_refusals"


WHY = {
    Flag.BIG_DROP: "The seller's agent dropped its price by more than "
    f"{BIG_DROP_PCT}% of list in one round. Check it's working as it should.",
    Flag.PROBING: "The buyer climbed in small binding steps and walked away without accepting: "
    "the pattern of someone mapping the seller's floor.",
    Flag.RETURNING: "The same buyer keeps coming back to this lot after failing.",
    Flag.GATE_REFUSALS: "Matching turned away questions about this lot today: many accounts "
    "may be asking about it.",
}


@dataclass(frozen=True)
class Visit:
    """One negotiation, as an account manager could see it."""

    buyer_id: str
    lot_id: str
    list_price: Pence
    cards: Sequence[OfferCard]
    accepted_by_buyer: bool
    walked_away_by_buyer: bool


def big_drop(visit: Visit) -> bool:
    counters = [c.base_price.value for c in visit.cards if c.from_role == "seller"]
    limit = visit.list_price.value * BIG_DROP_PCT / 100
    return any(a - b > limit for a, b in pairwise(counters))


def probing(visit: Visit) -> bool:
    offers = [c.base_price.value for c in visit.cards if c.from_role == "buyer"]
    if len(offers) < PROBING_OFFERS or visit.accepted_by_buyer or not visit.walked_away_by_buyer:
        return False
    step = visit.list_price.value * SMALL_STEP_PCT / 100
    return all(0 < b - a <= step for a, b in pairwise(offers))


def returning(history: Sequence[Visit]) -> bool:
    """Earlier failed visits by this buyer to this lot (history in time order)."""
    failed = [v for v in history if not v.accepted_by_buyer]
    return len(failed) >= RETURNS


def flags_for(visit: Visit, earlier: Sequence[Visit] = (), refused_today: int = 0) -> list[Flag]:
    found = []
    if big_drop(visit):
        found.append(Flag.BIG_DROP)
    if probing(visit):
        found.append(Flag.PROBING)
    same = [v for v in earlier if v.buyer_id == visit.buyer_id and v.lot_id == visit.lot_id]
    if returning([*same, visit]):
        found.append(Flag.RETURNING)
    if refused_today > 0:
        found.append(Flag.GATE_REFUSALS)
    return found
