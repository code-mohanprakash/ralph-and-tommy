"""Monitors: plain-code checks that flag a negotiation to an account manager.

The hard limits are in code and stop bad deals outright. Monitors are the next layer: they don't
block anything, they point a person at behaviour worth a look, the way labs put monitors on
their agents (and Project Vend found a second AI on the same model shares its blind spots, so
these are code, not a model). Each is scored on the bench for what it catches and how often it
cries wolf (bench/monitoring.py).

- probing: a buyer climbed in small binding steps and walked away without accepting, the
  pattern of an attacker mapping a floor (bench/moves.py). Catches 78% of the bench's probing
  attacks, no false alarms on 120 normal negotiations.
- returning: the same buyer came back to the same lot after failing, more than once. Catches
  84% of patient attackers.

Two more were built and measured, then removed (see the git history): a "big drop" in a
seller's price caught none of a broken Tommy's runs, because the referee stops his card before
anyone sees it, and flagged 5% of normal ones; match-gate refusals caught none of the matching
attacks, because a careful attacker never runs a lot's budget dry.

Nothing here reads the vault: monitors see what an account manager could see.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import OfferCard

SMALL_STEP_PCT = 8
PROBING_OFFERS = 3
RETURNS = 2


class Flag(StrEnum):
    PROBING = "probing"
    RETURNING = "returning"


WHY = {
    Flag.PROBING: "The buyer climbed in small binding steps and walked away without accepting: "
    "the pattern of someone mapping the seller's floor.",
    Flag.RETURNING: "The same buyer keeps coming back to this lot after failing.",
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


def flags_for(visit: Visit, earlier: Sequence[Visit] = ()) -> list[Flag]:
    found = []
    if probing(visit):
        found.append(Flag.PROBING)
    same = [v for v in earlier if v.buyer_id == visit.buyer_id and v.lot_id == visit.lot_id]
    if returning([*same, visit]):
        found.append(Flag.RETURNING)
    return found
