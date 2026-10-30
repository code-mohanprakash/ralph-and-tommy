"""What an agent sees, and what it can do.

An agent sees public facts (the lot, the want, the cards so far, rounds left) and can ask for a
band on a price. It never sees a number from the vault. It answers with exactly one action.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

from fleek_agents.domain.bands import Band
from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.models import DomainModel, Lot, Want
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import OfferCard, ReasonCode, Terms


class Send(DomainModel):
    kind: Literal["send"] = "send"
    terms: Terms


class Accept(DomainModel):
    kind: Literal["accept"] = "accept"


class WalkAway(DomainModel):
    kind: Literal["walk_away"] = "walk_away"
    reason: ReasonCode | None = None


class HandOff(DomainModel):
    """The agent couldn't act (it refused, hit the spend cap, or kept getting it wrong)."""

    kind: Literal["hand_off"] = "hand_off"
    reason: EscalationReason


Action = Send | Accept | WalkAway | HandOff


@dataclass(frozen=True)
class View:
    """One turn's worth of information for one side."""

    lot: Lot
    want: Want | None  # the buyer's want; None for the seller
    bundles: int  # the bundles being negotiated
    list_price: Pence  # base price per piece after the seller's bulk discount
    history: tuple[OfferCard, ...]  # every card so far, oldest first
    rounds_left: int  # cards that can still be sent
    band: Callable[[Pence], Band]  # how a price sits against *my own* limit
    today: date
    elsewhere: tuple[str, ...] = ()  # the buyer's other open deals, one line each (buyer only)

    @property
    def on_table(self) -> OfferCard | None:
        return self.history[-1] if self.history else None

    def my_last(self, role: str) -> OfferCard | None:
        mine = [c for c in self.history if c.from_role == role]
        return mine[-1] if mine else None


class Agent(Protocol):
    def decide(self, view: View) -> Action: ...
