"""What both scripted agents share: which bands count as inside, rounding, and card terms."""

from datetime import timedelta

from fleek_agents.agents.base import View
from fleek_agents.domain.bands import Band
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import Terms

INSIDE = {Band.STRONG, Band.ACCEPTABLE, Band.STRETCH}
SHIP_BY = timedelta(days=21)
SELL_BY_SOON = timedelta(days=7)  # this close to a lot's sell-by date, Tommy gives more ground


def _round5(pence: int) -> Pence:
    return Pence(max(0, pence - pence % 5))


def _terms(view: View, price: Pence) -> Terms:
    return Terms(
        base_price=price, bundles=view.bundles, prepaid=False, ship_by=view.today + SHIP_BY
    )
