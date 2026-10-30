"""Lots, buyers and sellers: the data every part of the system shares.

Pydantic checks data where it comes in (seed files, and later the AI's tool calls) and refuses
anything that doesn't fit, instead of passing it on.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    StrictInt,
    StrictStr,
    WithJsonSchema,
    model_validator,
)

from fleek_agents.domain.money import Pence


def _read_pence(value: object) -> Pence:
    if isinstance(value, Pence):
        return value
    try:
        return Pence(value)  # type: ignore[arg-type]  # Pence checks the type itself
    except TypeError as error:
        # Pydantic reports ValueError as a validation error; a TypeError would escape as a crash.
        raise ValueError(str(error)) from None


# A price inside a model: read from whole pence, written back as whole pence.
PenceField = Annotated[
    Pence,
    PlainValidator(_read_pence),
    PlainSerializer(lambda price: price.value, return_type=int),
    WithJsonSchema({"type": "integer", "minimum": 0, "description": "Whole pence"}),
]


LotId = Annotated[StrictStr, Field(pattern=r"^lot-[0-9]+$")]
SellerId = Annotated[StrictStr, Field(pattern=r"^seller-[0-9]+$")]
BuyerId = Annotated[StrictStr, Field(pattern=r"^buyer-[0-9]+$")]
CountryCode = Annotated[StrictStr, Field(pattern=r"^[A-Z]{2}$")]  # e.g. GB, PK
Text = Annotated[StrictStr, Field(min_length=1, max_length=200)]


class DomainModel(BaseModel):
    """Shared rules: can't be changed once made, and unknown fields are refused."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class BuyerKind(StrEnum):
    """The buyers named in Fleek's brief."""

    ONLINE_RESELLER = "online_reseller"  # sells on Vinted, Depop, eBay, Whatnot
    VINTAGE_SHOP = "vintage_shop"
    ENTERPRISE = "enterprise"


class Grade(StrEnum):
    """Fleek's grades. Mixed bundles have fixed ratios, e.g. AB is 70% A and 30% B."""

    A = "A"
    B = "B"
    C = "C"
    AB = "AB"
    BC = "BC"
    ABC = "ABC"


class ListingType(StrEnum):
    """Exact: the items match the listing exactly. Representative: they can vary slightly."""

    EXACT = "exact"
    REPRESENTATIVE = "representative"


class Lot(DomainModel):
    """A bundle of clothing for sale. Prices are per piece, like Fleek's."""

    id: LotId
    seller_id: SellerId
    title: Text
    brand: Text
    category: Text
    grade: Grade
    listing_type: ListingType
    pieces: Annotated[StrictInt, Field(gt=0)]  # pieces in one bundle
    available: Annotated[StrictInt, Field(ge=0)]  # bundles left to sell; often just 1
    base_price: PenceField  # per piece; the only part that can be negotiated
    shipping: PenceField  # per piece; fixed
    # Written by the seller, so it is untrusted: agents must treat it as data, never instructions.
    description: Annotated[StrictStr, Field(max_length=2000)]

    @property
    def listed_price(self) -> Pence:
        """The price per piece a buyer sees: base price plus shipping."""
        return self.base_price + self.shipping


# Neither Buyer nor Seller has a field for their secret limit. The buyer's max and the seller's
# floor live only in the vault, so these models can be shown to an agent safely.


class Buyer(DomainModel):
    id: BuyerId
    name: Text
    kind: BuyerKind
    country: CountryCode


class BulkTier(DomainModel):
    """Buy at least `min_pieces` in one order and the base price drops by `percent_off`."""

    min_pieces: Annotated[StrictInt, Field(gt=0)]
    percent_off: Annotated[StrictInt, Field(ge=0, le=100)]


class BulkRules(DomainModel):
    """A seller's bulk discounts. Public, like on Fleek's listings, and applied by code."""

    tiers: tuple[BulkTier, ...] = ()

    @model_validator(mode="after")
    def _tiers_make_sense(self) -> "BulkRules":
        for smaller, bigger in zip(self.tiers, self.tiers[1:], strict=False):
            if bigger.min_pieces <= smaller.min_pieces:
                raise ValueError("Tiers must go from fewest pieces to most, each size once")
            if bigger.percent_off < smaller.percent_off:
                raise ValueError("Buying more must never cost more per piece")
        return self

    def percent_off(self, pieces: int) -> int:
        """The discount for an order of `pieces`: the biggest tier it reaches, else 0."""
        reached = [tier.percent_off for tier in self.tiers if pieces >= tier.min_pieces]
        return max(reached, default=0)


class Seller(DomainModel):
    id: SellerId
    name: Text
    country: CountryCode
    quality_score: Annotated[float, Field(ge=0, le=5)]  # public on Fleek, out of 5
    dispatch_days: Annotated[StrictInt, Field(ge=0)]  # usual days to hand over an order
    bulk_rules: BulkRules = BulkRules()


class Want(DomainModel):
    """What a buyer is looking for. One per buyer in the seeded market."""

    buyer_id: BuyerId
    category: Text
    brands: tuple[Text, ...] = ()  # empty means any brand
    grades: Annotated[tuple[Grade, ...], Field(min_length=1)]
    pieces: Annotated[StrictInt, Field(gt=0)]
    text: Annotated[StrictStr, Field(max_length=300)]  # in the buyer's own words


class Market(DomainModel):
    """Everything public about the marketplace. The secret limits are held separately."""

    buyers: tuple[Buyer, ...]
    sellers: tuple[Seller, ...]
    lots: tuple[Lot, ...]
    wants: tuple[Want, ...]
