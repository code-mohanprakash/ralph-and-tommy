"""What the seller and the buyer type in before the live demo starts, checked as it comes in.

The two secret numbers (the seller's floor for each lot, the buyer's top price) arrive here as
plain numbers and go straight into mandates, which only the vault reads. Two boxes take free
text that an agent will read: the buyer's note (Ralph reads it) and each lot's description
(Tommy reads it; Ralph doesn't, in blind mode). A secret typed into one of those would reach a
model, so the form refuses it, and the buyer's note may hold no price at all.
"""

import re
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from fleek_agents.domain.models import BuyerKind, FinalSay, Grade, SellMode

Pennies = Annotated[StrictInt, Field(ge=1, le=100_000)]  # up to £1,000 a piece
Words = Annotated[str, Field(min_length=1, max_length=80)]


class FormError(ValueError):
    """Something in the form can't be used. The message says what to change, to that person."""


class _Form(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class StockLine(_Form):
    """One lot the seller has. Prices in pence per piece."""

    title: Words
    brand: Words
    category: Words
    grade: Grade
    pieces: Annotated[StrictInt, Field(ge=1, le=5000)]  # in one bundle
    bundles: Annotated[StrictInt, Field(ge=1, le=50)]
    list_price: Pennies  # base price per piece, before shipping
    shipping: Annotated[StrictInt, Field(ge=0, le=10_000)]
    description: Annotated[str, Field(max_length=600)] = ""
    floor: Pennies  # SECRET: the least per piece after Fleek's 15% commission
    mode: SellMode = SellMode.HAGGLE
    firm_price: Pennies | None = None
    sell_by: date | None = None
    walkaway_offer_pct: Annotated[StrictInt, Field(ge=1, le=50)] | None = None

    @model_validator(mode="after")
    def _firm_fits(self) -> "StockLine":
        if self.mode is SellMode.FIRM and self.firm_price is None:
            raise ValueError("Firm mode needs a firm price")
        return self  # a firm price sent with haggle mode is ignored (session.py)


class SellerForm(_Form):
    name: Words
    country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] = "PK"
    final_say: FinalSay = FinalSay.AGENT
    stock: Annotated[tuple[StockLine, ...], Field(min_length=1, max_length=8)]


class BuyerForm(_Form):
    name: Words
    kind: BuyerKind = BuyerKind.VINTAGE_SHOP
    country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] = "GB"
    category: Words
    brands: tuple[Words, ...] = ()
    grades: Annotated[tuple[Grade, ...], Field(min_length=1)]
    pieces: Annotated[StrictInt, Field(ge=1, le=10_000)]
    notes: Annotated[str, Field(max_length=300)] = ""
    top_price: Pennies  # SECRET: the most per piece, delivered (shipping and fee included)
    final_say: FinalSay = FinalSay.PERSON


class Setup(_Form):
    seller: SellerForm
    buyer: BuyerForm
    agents: Literal["scripted", "claude"] = "scripted"


MONEY = re.compile(r"£\s*\d|\d+\s*(p|pence|gbp|pounds?)\b|\b\d+\.\d{2}\b", re.IGNORECASE)


def _spellings(pence: int) -> list[str]:
    pounds, rest = divmod(pence, 100)
    return [f"{pounds}.{rest:02d}", f"{pence}p", f"{pence} p", f"£{pounds}.{rest:02d}"]


def _says(text: str, pence: int) -> bool:
    lowered = text.lower().replace(",", "")
    if any(s in lowered for s in _spellings(pence)):
        return True
    return re.search(rf"(?<![\d.]){pence}(?![\d.])", lowered) is not None


def check_free_text(setup: Setup) -> None:
    """Refuse a secret in any box a model reads. Raises FormError naming the box."""
    floors = [line.floor for line in setup.seller.stock]
    top = setup.buyer.top_price
    if MONEY.search(setup.buyer.notes):
        raise FormError(
            "Your note to Ralph can't hold a price: Ralph reads it. Put your top price in the "
            "secret box, where only the vault sees it."
        )
    for line in setup.seller.stock:
        for secret in (*floors, top):
            if _says(line.description, secret):
                raise FormError(
                    f"The description of {line.title!r} contains a secret number. Agents read "
                    "descriptions: keep floors and top prices in the secret boxes."
                )


# The ready-made onboarding: one button fills it in, and it's the one Claude was recorded on.
PRESET: dict[str, Any] = {
    "seller": {
        "name": "Karachi Textile Recycling",
        "country": "PK",
        "final_say": "agent",
        "stock": [
            {
                "title": "Levi's 501 jeans, grade A, 50 pairs",
                "brand": "Levi's",
                "category": "jeans",
                "grade": "A",
                "pieces": 50,
                "bundles": 4,
                "list_price": 1400,
                "shipping": 300,
                "description": "Washed and sorted. Mixed sizes 28-36, mostly mid-wash blue.",
                "floor": 935,
                "mode": "haggle",
                "walkaway_offer_pct": 8,
            },
            {
                "title": "Carhartt work jackets, grade B, 20 pieces",
                "brand": "Carhartt",
                "category": "jackets",
                "grade": "B",
                "pieces": 20,
                "bundles": 2,
                "list_price": 2600,
                "shipping": 450,
                "description": "Workwear, some fading on the cuffs.",
                "floor": 1800,
                "mode": "firm",
                "firm_price": 2350,
            },
        ],
    },
    "buyer": {
        "name": "Vintage shop, Brick Lane",
        "kind": "vintage_shop",
        "country": "GB",
        "category": "jeans",
        "brands": ["Levi's"],
        "grades": ["A"],
        "pieces": 100,
        "notes": "Levi's 501s for my shop: good condition, mixed sizes.",
        "top_price": 1550,
        "final_say": "person",
    },
    "agents": "scripted",
}
