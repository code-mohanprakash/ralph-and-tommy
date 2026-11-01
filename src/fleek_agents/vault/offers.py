"""The seller's offer to buyers who walked away: checked against the floor once, when it's set.

The offer is a public % off the list price, the same for every buyer who walked away. Checking
it here, before any buyer sees it, means a buyer can't learn anything from whether they got one:
every buyer who walked away from the lot gets the same price, or the seller was told to change
it before it went out.
"""

from fleek_agents.config import PrivacyRules
from fleek_agents.domain.models import Lot
from fleek_agents.domain.rules import walkaway_offer_price
from fleek_agents.vault.checks import seller_ok
from fleek_agents.vault.firm import working_limit
from fleek_agents.vault.mandate import SellerMandate
from fleek_agents.vault.privacy import guarded


class OfferBelowFloor(ValueError):
    """The offer would pay the seller less than their floor. Told to the seller only."""


def check_walkaway_offer(limit: SellerMandate, lot: Lot, privacy: PrivacyRules) -> None:
    price = walkaway_offer_price(lot)
    if price is None:
        return
    working = guarded(working_limit(limit, lot), privacy)
    if not seller_ok(working, base_price=price, pieces=lot.pieces):
        raise OfferBelowFloor("That offer pays you less than your own floor. Offer less off.")
