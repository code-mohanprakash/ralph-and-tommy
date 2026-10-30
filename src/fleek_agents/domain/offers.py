"""The offer card: what Ralph and Tommy send each other instead of messages.

There is no free-text field. An instruction planted in a listing ("ignore your rules...") could
otherwise travel from one agent to the other inside a message. The card carries the decision and
its reasons as fixed codes; each agent's thinking stays with that agent.
"""

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, StrictStr

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


class OfferCard(DomainModel):
    """One offer or counter-offer in a negotiation."""

    negotiation_id: NegotiationId
    round: Annotated[StrictInt, Field(ge=1)]
    from_role: Role
    base_price: PenceField  # per piece; shipping is fixed and not part of the offer
    bundles: Annotated[StrictInt, Field(gt=0)]
    prepaid: StrictBool
    ship_by: date
    reason_codes: tuple[ReasonCode, ...] = ()
    expires_at: AwareDatetime  # must carry a time zone; 48 hours after sending
