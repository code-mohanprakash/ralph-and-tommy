"""Scripted Ralph: a buyer as plain rules, no AI."""

from fleek_agents.agents.base import Accept, Action, Send, View, WalkAway
from fleek_agents.domain.bands import Band
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Role
from fleek_agents.scripted.common import INSIDE, _round5, _terms


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
