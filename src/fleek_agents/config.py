"""Settings from market.toml: the numbers we expect to tune, kept out of the code.

Nothing here is secret, and this module imports nothing from the vault, so any part of the
system can read settings, agents included.
"""

import tomllib
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


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


class NegotiationRules(BaseModel):
    """Fleek's Make an Offer rules: 48 hours to answer; our cap on rounds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_rounds: Annotated[StrictInt, Field(ge=1, le=20)] = 6  # offers + counters in one negotiation
    answer_hours: Annotated[StrictInt, Field(ge=1)] = 48
    # After a negotiation ends without a deal, the same buyer waits this long to retry that lot.
    cooldown_hours: Annotated[StrictInt, Field(ge=0)] = 24
    # Failed negotiations a buyer may have on one lot, ever (eBay's Best Offer allows 3 offers per
    # buyer per item). Each try tells a buyer something about the floor, so tries are rationed.
    tries_per_buyer_per_lot: Annotated[StrictInt, Field(ge=1)] = 3


class ModelRouting(BaseModel):
    """Which Claude model does which job. Bigger deals get the stronger model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    big_deal_pence: Annotated[StrictInt, Field(gt=0)] = 100_000  # £1,000 and up
    big_deal_model: str = "claude-sonnet-5-5"
    small_deal_model: str = "claude-haiku-5-5"
    digest_model: str = "claude-opus-5-5"  # the account manager's daily summary


class ModelPrice(BaseModel):
    """Anthropic's list price, in US cents per million tokens."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_cents_per_mtok: Annotated[StrictInt, Field(ge=0)]
    output_cents_per_mtok: Annotated[StrictInt, Field(ge=0)]


DEFAULT_PRICES = {
    "claude-haiku-5-5": ModelPrice(input_cents_per_mtok=10, output_cents_per_mtok=50),
    "claude-sonnet-5-5": ModelPrice(input_cents_per_mtok=200, output_cents_per_mtok=1000),
    "claude-opus-5-5": ModelPrice(input_cents_per_mtok=400, output_cents_per_mtok=2000),
}


class Spending(BaseModel):
    """Caps on what the AI may cost, in US cents (Anthropic bills in dollars)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    negotiation_cap_cents: Annotated[StrictInt, Field(gt=0)] = 25
    run_cap_cents: Annotated[StrictInt, Field(gt=0)] = 500
    prices: dict[str, ModelPrice] = Field(default_factory=lambda: dict(DEFAULT_PRICES))


class ApprovalRules(BaseModel):
    """When an agreed deal waits for a person instead of closing on its own."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    person_at_or_above_pence: Annotated[StrictInt, Field(gt=0)] = 150_000  # £1,500
    first_deals_by_person: Annotated[StrictInt, Field(ge=0)] = 3


class DigestRules(BaseModel):
    """What makes a failed negotiation worth an account manager's call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    near_miss_gap_pct: Annotated[StrictInt, Field(gt=0, le=100)] = 10
    list_size: Annotated[StrictInt, Field(gt=0)] = 20


class PrivacyRules(BaseModel):
    """Hiding the seller's floor in Tommy's moves (docs/SAFETY_CASE.md). Off unless turned on.

    - margin: each lot's floor is raised by a secret 0 to margin_max_pct %, drawn once per lot
      from the vault's key. An attacker who pins "the floor" exactly has found floor + margin.
    - noise: each counter Tommy sends moves by random noise of about noise_pct % of the list
      price, shrinking to nothing by the last round, and never below the raised floor.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    on: bool = False
    margin_max_pct: Annotated[StrictInt, Field(ge=0, le=20)] = 8  # chosen by the sweep (1 Nov)
    noise_pct: Annotated[StrictInt, Field(ge=0, le=20)] = 0  # measured: noise never helped


class MatchGateRules(BaseModel):
    """Rationing matching's yes/no so it can't be used to map a floor (vault/gate.py)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    on: bool = False
    # Measured: 5 a day refused half of real buyers' matches on the seeded market (many buyers
    # ask about one lot). 20 refuses about 1 question in 800; the grid does the hiding.
    answers_per_lot_per_day: Annotated[StrictInt, Field(ge=1)] = 20
    grid_pct: Annotated[StrictInt, Field(ge=1, le=20)] = 5  # top prices rounded down to this step


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bands: BandThresholds = BandThresholds()
    negotiation: NegotiationRules = NegotiationRules()
    models: ModelRouting = ModelRouting()
    spending: Spending = Spending()
    approval: ApprovalRules = ApprovalRules()
    digest: DigestRules = DigestRules()
    privacy: PrivacyRules = PrivacyRules()
    match_gate: MatchGateRules = MatchGateRules()


def load_settings(path: Path = Path("market.toml")) -> Settings:
    with path.open("rb") as file:
        return Settings.model_validate(tomllib.load(file))
