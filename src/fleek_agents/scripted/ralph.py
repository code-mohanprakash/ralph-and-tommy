"""Scripted Ralph: a buyer as plain rules, no AI."""

from fleek_agents.agents.base import Accept, Action, Send, View, WalkAway
from fleek_agents.domain.bands import Band
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Role
from fleek_agents.scripted.common import INSIDE, _round5, _terms


class ScriptedRalph:
    """Opens low, moves halfway towards the seller each round, never past his own limit.

    When halfway is past his limit he doesn't hold: he offers the highest price still inside it.
    His last card is his best and final: the highest price inside his limit, up to the counter.
    Holding used to lose deals that had room: the rounds ran out before Tommy came down to him.

    On a firm-price lot there's nothing to haggle: he offers the firm price if it's inside his
    limit, and walks away if it isn't.
    """

    best_offer = True  # HoldingRalph turns this off

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
        if not self.best_offer:
            if halfway > last and view.band(halfway) in INSIDE:
                return Send(terms=_terms(view, halfway))
            return Send(terms=_terms(view, last))  # can't move up: hold (offers can't go down)
        if view.rounds_left <= 2:  # his last card: Tommy answers it, then the rounds are over
            return Send(
                terms=_terms(view, _highest_inside(view, low=last, high=counter.base_price))
            )
        if halfway > last and view.band(halfway) in INSIDE:
            return Send(terms=_terms(view, halfway))
        best = _highest_inside(view, low=last, high=halfway)
        return Send(terms=_terms(view, best))  # his best; if it's his last, hold (never go down)


class HoldingRalph(ScriptedRalph):
    """The first scripted Ralph: when halfway is past his limit, he holds his last offer.

    Real buyers do this, and it loses deals that had room. The Deal Room uses him, because its
    near-miss story and the account manager's call list need a negotiation that ends close.
    """

    best_offer = False


def _highest_inside(view: View, *, low: Pence, high: Pence) -> Pence:
    """The highest whole-5p price from `low` (inside) up to `high` that is still inside his limit.

    A binary search over his own band words: he learns where his limit is to the nearest 5p,
    which is his own number and goes nowhere.
    """
    lo, hi = low.value // 5, high.value // 5  # in steps of 5p; lo is inside
    while lo < hi:
        middle = (lo + hi + 1) // 2
        if view.band(Pence(middle * 5)) in INSIDE:
            lo = middle
        else:
            hi = middle - 1
    return Pence(max(low.value, lo * 5))
