"""Fleek's fees: what the buyer really pays and what the seller really receives.

From Fleek's help centre (read 30 Oct 2026):
- Sellers pay a 15% commission on the base price. Shipping isn't their income.
- Buyers pay a 2% protection fee on the order total, capped at £20 per order.
We assume the 2% is on the whole order, shipping included (docs/ASSUMPTIONS.md, number 12).
Fees are worked out per order, as Fleek charges them, and rounded once each.
"""

from fleek_agents.domain.models import DomainModel, Lot, PenceField
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import OfferCard

COMMISSION_PCT = 15
PROTECTION_FEE_PCT = 2
PROTECTION_FEE_CAP = Pence(2000)  # £20


class BuyerPays(DomainModel):
    goods: PenceField  # (base price + shipping) x pieces
    protection_fee: PenceField
    total: PenceField


class SellerReceives(DomainModel):
    gross: PenceField  # base price x pieces
    commission: PenceField
    net: PenceField


def _check(pieces: int) -> None:
    if type(pieces) is not int or pieces < 1:
        raise ValueError(f"An order needs at least one piece, got {pieces!r}")


def buyer_pays(*, base_price: Pence, shipping: Pence, pieces: int) -> BuyerPays:
    _check(pieces)
    goods = (base_price + shipping).times(pieces)
    fee = min(goods.percent(PROTECTION_FEE_PCT), PROTECTION_FEE_CAP)
    return BuyerPays(goods=goods, protection_fee=fee, total=goods + fee)


def seller_receives(*, base_price: Pence, pieces: int) -> SellerReceives:
    _check(pieces)
    gross = base_price.times(pieces)
    commission = gross.percent(COMMISSION_PCT)
    return SellerReceives(gross=gross, commission=commission, net=gross - commission)


def order_total(card: OfferCard, lot: Lot) -> Pence:
    """What the buyer pays for the order on a card, shipping and protection fee included."""
    return buyer_pays(
        base_price=card.base_price, shipping=lot.shipping, pieces=card.bundles * lot.pieces
    ).total
