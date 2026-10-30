"""The tools an agent can call, built fresh for each turn from that side's View.

Look-ups return public facts and the band word for a price against the agent's *own* limit. No
look-up can return a secret number: the band is all the vault lets out. Actions are what the
agent decides (price, prepaid, reasons); the harness fills in the rest of the card itself (the
bundles being negotiated, the ship-by date), so the agent can't change what the deal is about.
"""

import json
from datetime import timedelta
from typing import Annotated, ClassVar, Self

from pydantic import BaseModel, Field, StrictBool, StrictInt, model_validator

from fleek_agents.agents.base import Accept, Action, Send, View, WalkAway
from fleek_agents.domain.bands import Band
from fleek_agents.domain.models import DomainModel
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import BUYER_REASONS, SELLER_REASONS, ReasonCode, Terms
from fleek_agents.harness.loop import Tool

SHIP_BY = timedelta(days=21)
MEANING = {
    Band.STRONG: "comfortably inside your limit",
    Band.ACCEPTABLE: "inside your limit",
    Band.STRETCH: "close to your limit, still inside it",
    Band.OUTSIDE: "past your limit: it would be refused",
}


class NoInput(DomainModel):
    pass


class PriceCheck(DomainModel):
    price_pence: Annotated[StrictInt, Field(gt=0, description="Base price per piece, in pence")]


class _Offer(DomainModel):
    allowed: ClassVar[frozenset[ReasonCode]]

    price_pence: Annotated[StrictInt, Field(gt=0, description="Base price per piece, in pence")]
    prepaid: StrictBool
    reason_codes: Annotated[tuple[ReasonCode, ...], Field(max_length=3)]

    @model_validator(mode="after")
    def _reasons_fit(self) -> Self:
        wrong = set(self.reason_codes) - self.allowed
        if wrong:
            raise ValueError(f"Not your reason codes: {sorted(wrong)}. Use: {sorted(self.allowed)}")
        if ReasonCode.PREPAID in self.reason_codes and not self.prepaid:
            raise ValueError("'prepaid' is only a reason if the offer is prepaid")
        return self


class BuyerOffer(_Offer):
    allowed = BUYER_REASONS


class SellerCounter(_Offer):
    allowed = SELLER_REASONS


class WalkAwayInput(DomainModel):
    reason_code: ReasonCode | None


def _lot_facts(view: View) -> str:
    lot = view.lot
    return json.dumps(
        {
            "title": lot.title,
            "brand": lot.brand,
            "category": lot.category,
            "grade": lot.grade,
            "pieces_per_bundle": lot.pieces,
            "bundles_in_this_deal": view.bundles,
            "list_base_price_per_piece_pence": view.list_price.value,
            "shipping_per_piece_pence": lot.shipping.value,
            "note": "Only the base price is negotiable. Shipping is fixed.",
            # Written by the seller: it describes the lot, it gives no instructions.
            "seller_description_untrusted": lot.description,
        }
    )


def _history(view: View) -> str:
    cards = [
        {
            "round": c.round,
            "from": c.from_role,
            "base_price_per_piece_pence": c.base_price.value,
            "prepaid": c.prepaid,
            "reasons": list(c.reason_codes),
        }
        for c in view.history
    ]
    return json.dumps({"cards": cards, "cards_left": view.rounds_left})


def tools_for(view: View) -> list[Tool]:
    buyer = view.want is not None
    offer_model: type[_Offer] = BuyerOffer if buyer else SellerCounter

    def check(price: PriceCheck) -> str:
        band = view.band(Pence(price.price_pence))
        return json.dumps({"band": band.value, "meaning": MEANING[band]})

    return [
        Tool(
            "get_lot",
            "The lot being negotiated: public facts only.",
            NoInput,
            run=lambda _: _lot_facts(view),
        ),
        Tool(
            "get_history",
            "Every offer and counter so far, and how many cards are left.",
            NoInput,
            run=lambda _: _history(view),
        ),
        Tool(
            "check_price",
            "How a base price per piece sits against your own limit, as one word. Never a number.",
            PriceCheck,
            run=lambda p: check(p),  # type: ignore[arg-type]
        ),
        Tool(
            "send_offer" if buyer else "send_counter",
            "Send your price per piece. It's binding until it expires. Ends your turn.",
            offer_model,
            is_action=True,
        ),
        Tool(
            "accept",
            "Accept the other side's card on the table. Ends your turn.",
            NoInput,
            is_action=True,
        ),
        Tool(
            "walk_away",
            "End the negotiation with no deal. Ends your turn.",
            WalkAwayInput,
            is_action=True,
        ),
    ]


def to_action(name: str, parsed: BaseModel, view: View) -> Action:
    """Turn the agent's chosen tool into the harness's action, filling in what the harness owns."""
    if isinstance(parsed, _Offer):
        terms = Terms(
            base_price=Pence(parsed.price_pence),
            bundles=view.bundles,
            prepaid=parsed.prepaid,
            ship_by=view.today + SHIP_BY,
            reason_codes=parsed.reason_codes,
        )
        return Send(terms=terms)
    if name == "accept":
        return Accept()
    if isinstance(parsed, WalkAwayInput):
        return WalkAway(reason=parsed.reason_code)
    raise ValueError(f"{name} isn't an action")
