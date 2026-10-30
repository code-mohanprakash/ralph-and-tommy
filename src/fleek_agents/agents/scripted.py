"""Ralph and Tommy as plain rules: no AI, no API key, the same every run.

They exist to test everything around the AI first: the harness, the rules, the vault, the log.
They follow the same limits the AI agents will: they only learn about their limit through bands.
"""

from datetime import date, timedelta

from fleek_agents.agents.base import Accept, Action, Send, View, WalkAway
from fleek_agents.domain.bands import Band
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Role, Terms

INSIDE = {Band.STRONG, Band.ACCEPTABLE, Band.STRETCH}
SHIP_BY = timedelta(days=21)


def _round5(pence: int) -> Pence:
    return Pence(max(0, pence - pence % 5))


def _terms(view: View, price: Pence) -> Terms:
    today = view.on_table.expires_at.date() if view.on_table else date(2026, 11, 2)
    return Terms(base_price=price, bundles=view.bundles, prepaid=False, ship_by=today + SHIP_BY)


class ScriptedRalph:
    """Opens low, moves halfway towards the seller each round, never past his own limit."""

    def decide(self, view: View) -> Action:
        counter = view.on_table
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

    def decide(self, view: View) -> Action:
        offer = view.on_table
        if offer is None:
            return WalkAway()  # nothing to answer
        band = view.band(offer.base_price)
        if band in (Band.STRONG, Band.ACCEPTABLE):
            return Accept()
        if view.rounds_left <= 0:
            return Accept() if band in INSIDE else WalkAway()
        mine = view.my_last(Role.SELLER)
        if mine is None:
            return Send(terms=_terms(view, view.list_price))
        step = _round5(
            mine.base_price.value - (mine.base_price.value - offer.base_price.value) // 3
        )
        if band is Band.STRETCH and view.rounds_left <= 1:
            return Accept()
        if step < mine.base_price and view.band(step) in INSIDE:
            return Send(terms=_terms(view, step))
        return Send(terms=_terms(view, mine.base_price))  # hold
