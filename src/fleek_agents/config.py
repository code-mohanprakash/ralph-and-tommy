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


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bands: BandThresholds = BandThresholds()


def load_settings(path: Path = Path("market.toml")) -> Settings:
    with path.open("rb") as file:
        return Settings.model_validate(tomllib.load(file))
