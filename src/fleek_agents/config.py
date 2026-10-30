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


class ModelRouting(BaseModel):
    """Which Claude model does which job. Bigger deals get the stronger model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    big_deal_pence: Annotated[StrictInt, Field(gt=0)] = 100_000  # £1,000 and up
    big_deal_model: str = "claude-sonnet-5-5"
    small_deal_model: str = "claude-haiku-5-5"
    digest_model: str = "claude-opus-5-5"  # the account manager's daily summary


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bands: BandThresholds = BandThresholds()
    negotiation: NegotiationRules = NegotiationRules()
    models: ModelRouting = ModelRouting()


def load_settings(path: Path = Path("market.toml")) -> Settings:
    with path.open("rb") as file:
        return Settings.model_validate(tomllib.load(file))
