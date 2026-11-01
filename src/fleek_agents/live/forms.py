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
    stock: Annotated[tuple[StockLine, ...], Field(min_length=1, max_length=20)]


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


# The ready-made market: one button fills it in, and the first buyer is the one Claude was
# recorded on. Ten lots, so matching has real work: filters, the vault's yes/no, ranking.
BUYERS: list[dict[str, Any]] = [
    {
        "name": "Vintage shop, Brick Lane",
        "kind": "vintage_shop",
        "country": "GB",
        "category": "jeans",
        "brands": ["Levi's"],
        "grades": ["A", "B"],
        "pieces": 100,
        "notes": "Levi's 501s for my shop: good condition, mixed sizes.",
        "top_price": 1550,
        "final_say": "person",
    },
    {
        "name": "Depop reseller, Manchester",
        "kind": "online_reseller",
        "country": "GB",
        "category": "sweatshirts",
        "brands": ["Nike", "Adidas"],
        "grades": ["A", "AB"],
        "pieces": 30,
        "notes": "90s sportswear that sells fast on Depop.",
        "top_price": 1250,
        "final_say": "agent",
    },
    {
        "name": "Outdoor store chain, Berlin",
        "kind": "enterprise",
        "country": "DE",
        "category": "fleeces",
        "brands": ["The North Face"],
        "grades": ["A"],
        "pieces": 40,
        "notes": "Fleeces for three stores before winter.",
        "top_price": 2300,
        "final_say": "person",
    },
]

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
                "title": "Levi's 505 jeans, grade B, 50 pairs",
                "brand": "Levi's",
                "category": "jeans",
                "grade": "B",
                "pieces": 50,
                "bundles": 3,
                "list_price": 1150,
                "shipping": 300,
                "description": "Some fading and small marks, noted on the packing list.",
                "floor": 720,
                "mode": "haggle",
            },
            {
                "title": "Wrangler jeans, grade A, 40 pairs",
                "brand": "Wrangler",
                "category": "jeans",
                "grade": "A",
                "pieces": 40,
                "bundles": 2,
                "list_price": 1200,
                "shipping": 300,
                "description": "Cowboy cut and regular fit, sizes 30-38.",
                "floor": 810,
                "mode": "firm",
                "firm_price": 1100,
            },
            {
                "title": "Levi's 501 jeans, grade C, 50 pairs",
                "brand": "Levi's",
                "category": "jeans",
                "grade": "C",
                "pieces": 50,
                "bundles": 2,
                "list_price": 800,
                "shipping": 300,
                "description": "Rips and repairs; good for rework.",
                "floor": 500,
                "mode": "haggle",
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
            {
                "title": "The North Face fleeces, grade A, 20 pieces",
                "brand": "The North Face",
                "category": "fleeces",
                "grade": "A",
                "pieces": 20,
                "bundles": 2,
                "list_price": 1800,
                "shipping": 350,
                "description": "Denali and 300-weight fleeces, mixed colours.",
                "floor": 1250,
                "mode": "haggle",
                "walkaway_offer_pct": 10,
            },
            {
                "title": "Nike sweatshirts, grade A, 30 pieces",
                "brand": "Nike",
                "category": "sweatshirts",
                "grade": "A",
                "pieces": 30,
                "bundles": 3,
                "list_price": 950,
                "shipping": 250,
                "description": "90s and 00s centre-swoosh crewnecks.",
                "floor": 620,
                "mode": "haggle",
                "sell_by": "2026-11-06",
            },
            {
                "title": "Adidas track tops, grade AB, 30 pieces",
                "brand": "Adidas",
                "category": "track tops",
                "grade": "AB",
                "pieces": 30,
                "bundles": 2,
                "list_price": 1000,
                "shipping": 250,
                "description": "Firebird and vintage trefoil, 70% grade A.",
                "floor": 650,
                "mode": "haggle",
            },
            {
                "title": "Ralph Lauren polos, grade A, 40 pieces",
                "brand": "Ralph Lauren",
                "category": "polos",
                "grade": "A",
                "pieces": 40,
                "bundles": 2,
                "list_price": 800,
                "shipping": 200,
                "description": "Classic fit, small pony, sizes S-XL.",
                "floor": 540,
                "mode": "haggle",
            },
            {
                "title": "Harley-Davidson tees, grade B, 50 pieces",
                "brand": "Harley-Davidson",
                "category": "t-shirts",
                "grade": "B",
                "pieces": 50,
                "bundles": 2,
                "list_price": 650,
                "shipping": 180,
                "description": "Dealer tees, some cracking on prints.",
                "floor": 410,
                "mode": "haggle",
            },
        ],
    },
    "buyer": BUYERS[0],
    "agents": "scripted",
}
