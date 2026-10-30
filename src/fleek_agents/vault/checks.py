"""The vault's yes/no answers. They return True or False, never a number.

Both check the money that actually moves, after Fleek's fees:
- the buyer's whole order cost (goods, shipping, protection fee) against their max per piece
- the seller's payout after commission against their floor per piece
"""

from fleek_agents.domain.fees import buyer_pays, seller_receives
from fleek_agents.domain.money import Pence
from fleek_agents.domain.rules import Quote
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate


def buyer_ok(buyer: BuyerMandate, *, base_price: Pence, shipping: Pence, pieces: int) -> bool:
    cost = buyer_pays(base_price=base_price, shipping=shipping, pieces=pieces).total
    return cost <= buyer.max_per_piece.reveal().times(pieces)


def seller_ok(seller: SellerMandate, *, base_price: Pence, pieces: int) -> bool:
    net = seller_receives(base_price=base_price, pieces=pieces).net
    return net >= seller.floor_per_piece.reveal().times(pieces)


def can_accept(
    buyer: BuyerMandate,
    seller: SellerMandate,
    *,
    base_price: Pence,
    shipping: Pence,
    pieces: int,
) -> bool:
    """Is this price inside both secret limits?"""
    return buyer_ok(buyer, base_price=base_price, shipping=shipping, pieces=pieces) and seller_ok(
        seller, base_price=base_price, pieces=pieces
    )


def deal_possible(buyer: BuyerMandate, seller: SellerMandate, quote: Quote) -> bool:
    """Is there any base price, up to the quoted one, inside both limits?

    Used by matching to skip pairs that can never close, before any AI is called. The seller's
    payout only rises with the price and the buyer's cost only rises too, so it's enough to find
    the lowest price the seller accepts and ask whether the buyer can pay it.
    """
    highest = quote.base_price.value
    if not seller_ok(seller, base_price=Pence(highest), pieces=quote.pieces):
        return False  # not even the listed price clears the floor
    low, high = 0, highest  # binary search for the lowest price the seller accepts
    while low < high:
        middle = (low + high) // 2
        if seller_ok(seller, base_price=Pence(middle), pieces=quote.pieces):
            high = middle
        else:
            low = middle + 1
    return buyer_ok(buyer, base_price=Pence(low), shipping=quote.shipping, pieces=quote.pieces)
