from pathlib import Path

import pytest
from pydantic import ValidationError

from fleek_agents.config import (
    BandThresholds,
    NegotiationRules,
    Settings,
    Spending,
    load_settings,
)


def test_the_thresholds_come_from_market_toml() -> None:
    settings = load_settings(Path(__file__).parents[1] / "market.toml")
    assert settings.bands == BandThresholds(strong_pct=85, acceptable_pct=95)


def test_a_settings_file_with_bad_bands_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "market.toml"
    bad.write_text("[bands]\nstrong_pct = 99\nacceptable_pct = 90\n")
    with pytest.raises(ValidationError):
        load_settings(bad)


def test_the_negotiation_rules_come_from_market_toml() -> None:
    settings = load_settings(Path(__file__).parents[1] / "market.toml")
    assert settings.negotiation == NegotiationRules(
        max_rounds=6, answer_hours=48, cooldown_hours=24
    )


def test_spend_caps_and_prices_come_from_market_toml() -> None:
    settings = load_settings(Path(__file__).parents[1] / "market.toml")
    assert settings.spending == Spending()
    assert settings.spending.prices["claude-haiku-5-5"].output_cents_per_mtok == 50


def test_the_defaults_in_code_match_market_toml() -> None:
    # Library code that builds Settings() directly gets the same numbers the commands read.
    assert load_settings(Path(__file__).parents[1] / "market.toml") == Settings()
