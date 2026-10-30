from pathlib import Path

import pytest
from pydantic import ValidationError

from fleek_agents.config import load_settings
from fleek_agents.vault.bands import BandThresholds


def test_the_thresholds_come_from_market_toml() -> None:
    settings = load_settings(Path(__file__).parents[1] / "market.toml")
    assert settings.bands == BandThresholds(strong_pct=85, acceptable_pct=95)


def test_a_settings_file_with_bad_bands_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "market.toml"
    bad.write_text("[bands]\nstrong_pct = 99\nacceptable_pct = 90\n")
    with pytest.raises(ValidationError):
        load_settings(bad)
