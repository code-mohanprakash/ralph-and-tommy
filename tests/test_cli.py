import json
from collections.abc import Iterator
from pathlib import Path

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


def test_fleek_safety_replays_the_recorded_attacks_with_no_key() -> None:
    result = runner.invoke(app, ["safety"])
    assert result.exit_code == 0, result.output
    assert "Naive seller: secret leaked in 1 of 4 attacks." in result.output
    assert "Protected agents: 0 deals outside a limit in 3 attacks." in result.output


def test_a_deal_waits_then_a_person_approves_it(tmp_path: Path) -> None:
    db = str(tmp_path / "fleek.db")
    first = runner.invoke(
        app, ["negotiate", "--mock", "--buyer", "buyer-0002", "--matcher", "words", "--db", db]
    )
    assert first.exit_code == 0, first.output
    assert "Waiting for a person" in first.output and "fleek approve neg-0001" in first.output
    listed = runner.invoke(app, ["approvals", "--db", db], env={"COLUMNS": "200"})
    assert "neg-0001" in listed.output and "£1,500 or more" in listed.output  # £2,332.50 deal
    done = runner.invoke(app, ["approve", "neg-0001", "--db", db])
    assert done.exit_code == 0 and "approved and closed" in done.output
    assert "Nothing waiting" in runner.invoke(app, ["approvals", "--db", db]).output


def test_the_call_list_comes_from_the_deals_file(tmp_path: Path) -> None:
    db = str(tmp_path / "fleek.db")
    assert "No near misses" in runner.invoke(app, ["digest", "--db", db]).output
    for buyer in ("buyer-0020", "buyer-0037"):
        runner.invoke(
            app, ["negotiate", "--mock", "--buyer", buyer, "--matcher", "words", "--db", db]
        )
    listed = runner.invoke(app, ["digest", "--db", db], env={"COLUMNS": "200"})
    assert "buyer-0020" in listed.output and "walked_away" in listed.output


def test_the_no_channel_check_fails_for_the_right_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    # If cards allowed extra fields, the report must say so, not still claim "refused".
    from fleek_agents.domain import offers
    from fleek_agents.safety import report

    loose = type(
        "LooseCard",
        (offers.OfferCard,),
        {"model_config": {**offers.OfferCard.model_config, "extra": "allow"}},
    )
    monkeypatch.setattr(report, "OfferCard", loose)
    assert report.text_channel_check() == "OPEN: a card accepted a free-text message"
    row = next(r for r in report.safety_report() if r.attack == "all four text attacks")
    assert row.leaked == "OPEN"  # the leak column too, not only the last one


def test_a_run_exports_to_json(tmp_path: Path) -> None:
    db, out = str(tmp_path / "fleek.db"), tmp_path / "runs" / "run.json"
    runner.invoke(
        app, ["negotiate", "--mock", "--buyer", "buyer-0002", "--matcher", "words", "--db", db]
    )
    result = runner.invoke(app, ["export", "--db", db, "--out", str(out), "--title", "demo"])
    assert result.exit_code == 0 and "Wrote 1 negotiation" in result.output
    data = json.loads(out.read_text())
    assert (
        data["format"] == "ralph-and-tommy/run/1"
        and data["negotiations"][0]["buyer_id"] == "buyer-0002"
    )


def test_editing_market_toml_changes_what_the_commands_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    toml = (Path(__file__).parents[1] / "market.toml").read_text()
    for old, new in [
        ("person_at_or_above_pence = 150000", "person_at_or_above_pence = 99999999"),
        ("first_deals_by_person = 3", "first_deals_by_person = 0"),
    ]:
        assert toml.count(old) == 1
        toml = toml.replace(old, new)
    (tmp_path / "market.toml").write_text(toml)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["negotiate", "--mock", "--buyer", "buyer-0002", "--matcher", "words"]
    )
    assert result.exit_code == 0, result.output
    # The same £2,332.50 deal waits for a person with the shipped market.toml.
    assert "Approved by the rule" in result.output


def test_without_market_toml_a_command_says_where_to_run_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for command in ("approvals", "digest"):
        result = runner.invoke(app, [command])
        assert result.exit_code == 2 and "No market.toml here" in result.output
    assert list(tmp_path.iterdir()) == []  # and it left no empty deals file behind
