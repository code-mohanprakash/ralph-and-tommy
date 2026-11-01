"""Ralph and Tommy as plain rules: no AI, no API key, the same every run.

They exist to test everything around the AI first: the harness, the rules, the vault, the log.
They follow the same limits the AI agents will: they only learn about their limit through bands.
"""

from datetime import timedelta
from fractions import Fraction

from fleek_agents.agents.base import Accept, Action, Send, View, WalkAway
from fleek_agents.domain.bands import Band
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Role, Terms

INSIDE = {Band.STRONG, Band.ACCEPTABLE, Band.STRETCH}
SHIP_BY = timedelta(days=21)
SELL_BY_SOON = timedelta(days=7)  # this close to a lot's sell-by date, Tommy gives more ground


def _round5(pence: int) -> Pence:
    return Pence(max(0, pence - pence % 5))


def _terms(view: View, price: Pence) -> Terms:
    return Terms(
        base_price=price, bundles=view.bundles, prepaid=False, ship_by=view.today + SHIP_BY
    )


class ScriptedRalph:
    """Opens low, moves halfway towards the seller each round, never past his own limit.

    On a firm-price lot there's nothing to haggle: he offers the firm price if it's inside his
    limit, and walks away if it isn't.
    """

    def decide(self, view: View) -> Action:
        counter, firm = view.on_table, view.lot.firm_price
        if view.promised is not None and counter is None:  # the seller's offer: take it or not
            if view.band(view.promised) in INSIDE:
                return Send(terms=_terms(view, view.promised))
            return WalkAway()
        if firm is not None:
            if counter is not None and view.band(counter.base_price) in INSIDE:
                return Accept()
            if counter is None and view.band(firm) in INSIDE:
                return Send(terms=_terms(view, firm))
            return WalkAway()
        if counter is None:  # opening offer: the highest of 80/70/60/50% of list inside his limit
            for pct in (80, 70, 60, 50):
                price = _round5(view.list_price.value * pct // 100)
                if view.band(price) in INSIDE:
                    return Send(terms=_terms(view, price))
            return WalkAway()
        band = view.band(counter.base_price)
        if band in (Band.STRONG, Band.ACCEPTABLE):
            return Accept()
        mine = view.my_last(Role.BUYER)
        last = mine.base_price if mine else Pence(0)
        if view.rounds_left <= 0:
            return Accept() if band in INSIDE else WalkAway()
        halfway = _round5((last.value + counter.base_price.value) // 2)
        if band is Band.STRETCH and view.rounds_left <= 1:
            return Accept()
        if halfway > last and view.band(halfway) in INSIDE:
            return Send(terms=_terms(view, halfway))
        return Send(terms=_terms(view, last))  # can't move up: hold (offers can't go down)


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
