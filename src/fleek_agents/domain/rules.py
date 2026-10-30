"""Price rules applied by code. The AI asks for a quote; it never works out a discount itself."""

from typing import Annotated

from pydantic import Field, StrictInt

from fleek_agents.domain.models import DomainModel, Lot, LotId, PenceField, Seller


class Quote(DomainModel):
    """The price for a number of bundles of one lot, after the seller's bulk discount."""

    lot_id: LotId
    bundles: Annotated[StrictInt, Field(gt=0)]
    pieces: Annotated[StrictInt, Field(gt=0)]
    percent_off: Annotated[StrictInt, Field(ge=0, le=100)]
    base_price: PenceField  # per piece, after the discount
    shipping: PenceField  # per piece, never discounted
    total: PenceField  # (base_price + shipping) x pieces


def quote(lot: Lot, seller: Seller, bundles: int) -> Quote:
    """Price `bundles` bundles of `lot` using its seller's bulk rules."""
    if seller.id != lot.seller_id:
        raise ValueError(f"{lot.id} is sold by {lot.seller_id}, not {seller.id}")
    if type(bundles) is not int:
        raise TypeError(f"Bundles must be a whole number, got {bundles!r}")
    if not 1 <= bundles <= lot.available:
        raise ValueError(f"{lot.id} has {lot.available} bundle(s) available, asked for {bundles}")

    pieces = bundles * lot.pieces
    percent_off = seller.bulk_rules.percent_off(pieces)
    base_price = lot.base_price.discounted(percent_off)  # rounded once, per piece
    return Quote(
        lot_id=lot.id,
        bundles=bundles,
        pieces=pieces,
        percent_off=percent_off,
        base_price=base_price,
        shipping=lot.shipping,
        total=(base_price + lot.shipping).times(pieces),
    )
