"""Scripted Tommy: a seller as plain rules, no AI. Two styles: thirds, and Boulware."""

from fractions import Fraction

from fleek_agents.agents.base import Accept, Action, Send, View, WalkAway
from fleek_agents.domain.bands import Band
from fleek_agents.domain.offers import Role
from fleek_agents.scripted.common import INSIDE, SELL_BY_SOON, _round5, _terms


class ScriptedTommy:
    """Starts at the list price, comes down a third of the gap each round, never past his floor."""

    def share(self, rounds_left: int) -> Fraction:
        """How much of the gap to the buyer's offer he gives up this round (exact, no floats)."""
        return Fraction(1, 3)

    def decide(self, view: View) -> Action:
        offer = view.on_table
        if offer is None:
            return WalkAway()  # nothing to answer
        band = view.band(offer.base_price)
        firm = view.lot.firm_price
        if firm is not None:  # firm mode: his limit is the public firm price, so no haggling
            if band in INSIDE:
                return Accept()
            return WalkAway() if view.rounds_left <= 0 else Send(terms=_terms(view, firm))
        if band in (Band.STRONG, Band.ACCEPTABLE):
            return Accept()
        if view.rounds_left <= 0:
            return Accept() if band in INSIDE else WalkAway()
        mine = view.my_last(Role.SELLER)
        if mine is None:
            return Send(terms=_terms(view, view.list_price))
        gap = mine.base_price.value - offer.base_price.value
        share = self.share(view.rounds_left)
        sell_by = view.lot.sell_by
        if sell_by is not None and sell_by - view.today <= SELL_BY_SOON:
            share = max(share, Fraction(1, 2))  # public deadline, so speed tells nothing secret
        step = _round5(mine.base_price.value - int(gap * share))
        if band is Band.STRETCH and view.rounds_left <= 1:
            return Accept()
        if step < mine.base_price and view.band(step) in INSIDE:
            return Send(terms=_terms(view, step))
        return Send(terms=_terms(view, mine.base_price))  # hold


class BoulwareTommy(ScriptedTommy):
    """Gives little ground until the deadline (Faratin, Sierra & Jennings, 1998: "Boulware").

    Each move a seller makes toward his floor says something about it. Holding firm early and
    moving late means fewer, later clues: measured with `fleek leak --sweep`.
    """

    def share(self, rounds_left: int) -> Fraction:
        return Fraction(1, 2) if rounds_left <= 1 else Fraction(1, 10)
