"""Price bands: how close a price is to a side's own limit, in four words, never a number.

The agent needs to know when it's near its limit. Four coarse bands tell it that much and no
more, and (in a later PR) it gets one check per round, so it can't zero in on the number.
"""

from fleek_agents.config import BandThresholds
from fleek_agents.domain.bands import Band
from fleek_agents.domain.fees import buyer_pays, seller_receives
from fleek_agents.domain.money import Pence
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate


def band_of(part: Pence, whole: Pence, t: BandThresholds) -> Band:
    """Band for part/whole, in whole numbers only: part*100 <= whole*pct, no division."""
    part100, whole_ = part.value * 100, whole.value
    if part100 <= whole_ * t.strong_pct:
        return Band.STRONG
    if part100 <= whole_ * t.acceptable_pct:
        return Band.ACCEPTABLE
    if part100 <= whole_ * 100:
        return Band.STRETCH
    return Band.OUTSIDE


def buyer_band(
    mandate: BuyerMandate, *, base_price: Pence, shipping: Pence, pieces: int, t: BandThresholds
) -> Band:
    """What the buyer would pay for the whole order, fees included, against max x pieces."""
    cost = buyer_pays(base_price=base_price, shipping=shipping, pieces=pieces).total
    return band_of(cost, mandate.max_per_piece.reveal().times(pieces), t)


def seller_band(
    mandate: SellerMandate, *, base_price: Pence, pieces: int, t: BandThresholds
) -> Band:
    """The seller's floor x pieces, against their payout after commission. The mirror image."""
    net = seller_receives(base_price=base_price, pieces=pieces).net
    return band_of(mandate.floor_per_piece.reveal().times(pieces), net, t)
