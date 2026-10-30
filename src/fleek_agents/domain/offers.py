"""The offer card: what Ralph and Tommy send each other instead of messages.

There is no free-text field. An instruction planted in a listing ("ignore your rules...") could
otherwise travel from one agent to the other inside a message. The card carries the decision and
its reasons as fixed codes; each agent's thinking stays with that agent.
"""

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, StrictStr, model_validator

from fleek_agents.domain.models import DomainModel, PenceField

NegotiationId = Annotated[StrictStr, Field(pattern=r"^neg-[0-9]+$")]


class Role(StrEnum):
    BUYER = "buyer"  # Ralph
    SELLER = "seller"  # Tommy


class ReasonCode(StrEnum):
    """Why an offer is what it is. A fixed list, so a reason can't carry an instruction."""

    # buyer
    PREPAID = "prepaid"
    REPEAT_BUYER = "repeat_buyer"
    BULK = "bulk"
    DEADLINE = "deadline"
    QUALITY_CONCERN = "quality_concern"
    # seller
    AGEING_STOCK = "ageing_stock"
    LIMITED_QTY = "limited_qty"


BUYER_REASONS = frozenset(
    {
        ReasonCode.PREPAID,
        ReasonCode.REPEAT_BUYER,
        ReasonCode.BULK,
        ReasonCode.DEADLINE,
        ReasonCode.QUALITY_CONCERN,
    }
)
SELLER_REASONS = frozenset({ReasonCode.AGEING_STOCK, ReasonCode.LIMITED_QTY})
REASONS_FOR = {Role.BUYER: BUYER_REASONS, Role.SELLER: SELLER_REASONS}


class OfferCard(DomainModel):
    """One offer or counter-offer in a negotiation."""

    negotiation_id: NegotiationId
    round: Annotated[StrictInt, Field(ge=1)]
    from_role: Role
    base_price: PenceField  # per piece; shipping is fixed and not part of the offer
    bundles: Annotated[StrictInt, Field(gt=0)]
    prepaid: StrictBool
    ship_by: date
    reason_codes: Annotated[tuple[ReasonCode, ...], Field(max_length=3)] = ()
    expires_at: AwareDatetime  # must carry a time zone; 48 hours after sending

    @model_validator(mode="after")
    def _reasons_fit_the_offer(self) -> "OfferCard":
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("Each reason code can appear once")
        wrong_side = set(self.reason_codes) - REASONS_FOR[self.from_role]
        if wrong_side:
            names = ", ".join(sorted(wrong_side))
            raise ValueError(f"A {self.from_role} can't give these reasons: {names}")
        if ReasonCode.PREPAID in self.reason_codes and not self.prepaid:
            raise ValueError("'prepaid' is only a reason if the offer is prepaid")
        return self
