"""An event: one move in one negotiation, as it gets written to the log."""

from typing import Annotated, Self

from pydantic import AwareDatetime, Field, StrictInt, model_validator

from fleek_agents.domain.models import DomainModel
from fleek_agents.domain.offers import NegotiationId, OfferCard, Role
from fleek_agents.domain.state import Actor, IllegalMove, Move, NegotiationState, next_state

# The moves that carry an offer card, and whose card it must be.
CARD_FROM = {Move.OFFER: Role.BUYER, Move.COUNTER: Role.SELLER}


class Event(DomainModel):
    negotiation_id: NegotiationId
    seq: Annotated[StrictInt, Field(ge=1)]  # 1, 2, 3... within one negotiation
    at: AwareDatetime
    by: Actor
    move: Move
    from_state: NegotiationState
    to_state: NegotiationState
    card: OfferCard | None = None

    @model_validator(mode="after")
    def _fits_the_rules(self) -> Self:
        try:
            expected = next_state(self.from_state, self.move, by=self.by)
        except IllegalMove as error:
            raise ValueError(str(error)) from None
        if self.to_state is not expected:
            raise ValueError(f"{self.move} from {self.from_state} leads to {expected}")

        role = CARD_FROM.get(self.move)
        if role is None and self.card is not None:
            raise ValueError(f"A {self.move} carries no offer card")
        if role is not None:
            if self.card is None:
                raise ValueError(f"A {self.move} needs an offer card")
            if self.card.from_role is not role:
                raise ValueError(f"A {self.move} needs a card from the {role}")
            if self.card.negotiation_id != self.negotiation_id:
                raise ValueError("The card belongs to a different negotiation")
        return self
