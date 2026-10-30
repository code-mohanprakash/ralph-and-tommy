"""Price bands: how close a price is to a side's own limit, in four words, never a number.

The agent needs to know when it's near its limit. Four coarse bands tell it that much and no
more, and (in a later PR) it gets one check per round, so it can't zero in on the number.
"""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from fleek_agents.domain.money import Pence
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate


class Band(StrEnum):
    STRONG = "strong"
    ACCEPTABLE = "acceptable"
    STRETCH = "stretch"  # still inside the limit
    OUTSIDE = "outside"  # past the limit: the vault will refuse it


class BandThresholds(BaseModel):
    """Where the bands split, as a percentage of the limit. Set in market.toml."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strong_pct: Annotated[StrictInt, Field(gt=0, lt=100)] = 85
    acceptable_pct: Annotated[StrictInt, Field(gt=0, lt=100)] = 95

    @model_validator(mode="after")
    def _in_order(self) -> Self:
        if self.strong_pct >= self.acceptable_pct:
            raise ValueError("strong_pct must be below acceptable_pct")
        return self


def _band(part: Pence, whole: Pence, t: BandThresholds) -> Band:
    """Band for part/whole, in whole numbers only: part*100 <= whole*pct, no division."""
    part100, whole_ = part.value * 100, whole.value
    if part100 <= whole_ * t.strong_pct:
        return Band.STRONG
    if part100 <= whole_ * t.acceptable_pct:
        return Band.ACCEPTABLE
    if part100 <= whole_ * 100:
        return Band.STRETCH
    return Band.OUTSIDE


def buyer_band(mandate: BuyerMandate, cost_per_piece: Pence, t: BandThresholds) -> Band:
    """What the buyer would pay per piece, against their max."""
    return _band(cost_per_piece, mandate.max_per_piece.reveal(), t)


def seller_band(mandate: SellerMandate, proceeds_per_piece: Pence, t: BandThresholds) -> Band:
    """The seller's floor, against what they would receive per piece. The mirror image."""
    return _band(mandate.floor_per_piece.reveal(), proceeds_per_piece, t)
