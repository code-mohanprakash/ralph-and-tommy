"""Settings from market.toml: the numbers we expect to tune, kept out of the code."""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from fleek_agents.vault.bands import BandThresholds


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bands: BandThresholds = BandThresholds()


def load_settings(path: Path = Path("market.toml")) -> Settings:
    with path.open("rb") as file:
        return Settings.model_validate(tomllib.load(file))
