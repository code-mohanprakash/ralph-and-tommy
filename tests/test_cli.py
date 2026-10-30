from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from fleek_agents.cli import app
from fleek_agents.market.seed import generate_market
from fleek_agents.matching.embeddings import HashingEmbedder
from fleek_agents.matching.funnel import possible_deals
from fleek_agents.matching.ranking import rank
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.market import load_market
from fleek_agents.vault.seed import generate_mandates

runner = CliRunner()
MARKET = generate_market(seed=2026)
SECRETS = generate_mandates(MARKET, seed=2026)


@pytest.fixture(scope="module")
def session() -> Iterator[Session]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        load_market(session, MARKET)
        yield session


def test_negotiate_mock_runs_end_to_end() -> None:
    result = runner.invoke(
        app, ["negotiate", "--mock", "--buyer", "buyer-0001", "--matcher", "words"]
    )
    assert result.exit_code == 0, result.output
    assert "Matching:" in result.output
    assert "Ralph" in result.output and "Tommy" in result.output


def test_the_output_never_shows_a_secret_limit(session: Session) -> None:
    for want in MARKET.wants[:5]:
        result = runner.invoke(
            app, ["negotiate", "--mock", "--buyer", want.buyer_id, "--matcher", "words"]
        )
        assert result.exit_code == 0, result.output
        # The buyer's max, and the floor of the lot the command chose (found the same way).
        chosen = rank(want, possible_deals(session, MARKET, SECRETS, want), HashingEmbedder())
        limits = [SECRETS.buyers[want.buyer_id].max_per_piece.reveal()]
        if chosen:
            limits.append(SECRETS.lots[chosen[0].lot.id].floor_per_piece.reveal())
        for limit in limits:
            assert str(limit) not in result.output, f"{want.buyer_id}: a secret limit was printed"


def test_without_mock_it_says_the_ai_agents_arent_built_yet() -> None:
    result = runner.invoke(app, ["negotiate"])
    assert result.exit_code == 2
    assert "--mock" in result.output


def test_an_unknown_buyer_is_explained() -> None:
    result = runner.invoke(
        app, ["negotiate", "--mock", "--buyer", "buyer-9999", "--matcher", "words"]
    )
    assert result.exit_code == 2
    assert "No buyer called" in result.output


def test_every_line_the_command_prints_goes_through_the_leak_scanner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleek_agents.safety import scanner as scanner_module

    seen: list[str] = []
    original = scanner_module.LeakScanner.clean

    def spy(self: scanner_module.LeakScanner, line: str) -> str:
        seen.append(line)
        return original(self, line)

    monkeypatch.setattr(scanner_module.LeakScanner, "clean", spy)
    result = runner.invoke(
        app, ["negotiate", "--mock", "--buyer", "buyer-0001", "--matcher", "words"]
    )
    assert result.exit_code == 0, result.output
    assert any("wants:" in line for line in seen) and any("Ralph" in line for line in seen)
    assert any("pays" in line or "Ended" in line for line in seen)
