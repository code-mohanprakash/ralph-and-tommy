from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from fleek_agents.agents.choose import choose_three
from fleek_agents.domain.models import Want
from fleek_agents.domain.rules import Candidate
from fleek_agents.harness.loop import Outcome
from fleek_agents.llm.env import load_env_file
from fleek_agents.llm.replay import cassette_client
from fleek_agents.market.seed import generate_market
from fleek_agents.matching.embeddings import HashingEmbedder
from fleek_agents.matching.funnel import possible_deals
from fleek_agents.matching.ranking import rank
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.market import load_market
from fleek_agents.vault.seed import generate_mandates
from tests.fakes import FakeClient, call, message

MARKET = generate_market(seed=2026)
SECRETS = generate_mandates(MARKET, seed=2026)
SELLERS = {s.id: s for s in MARKET.sellers}
CASSETTES = Path(__file__).parent / "cassettes"


@pytest.fixture(scope="module")
def top10() -> Iterator[tuple[Want, list[Candidate]]]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        load_market(session, MARKET)
        for want in MARKET.wants:
            ranked = rank(want, possible_deals(session, MARKET, SECRETS, want), HashingEmbedder())
            if len(ranked) == 10:
                yield want, ranked
                return


def pick(*ids: str) -> dict[str, object]:
    return {"lot_ids": list(ids), "why": "Best fit."}


def test_ralph_s_three_come_back_in_his_order(top10: tuple[Want, list[Candidate]]) -> None:
    want, shortlist = top10
    ids = [c.lot.id for c in shortlist]
    client = FakeClient(message(call("choose_lots", pick(ids[4], ids[0], ids[7]))))
    chosen, turn = choose_three(
        client, model="claude-haiku-5-5", want=want, candidates=shortlist, sellers=SELLERS
    )
    assert [c.lot.id for c in chosen] == [ids[4], ids[0], ids[7]]
    assert turn is not None and turn.corrections == 0


@pytest.mark.parametrize("bad", ["duplicate", "off_list", "two"])
def test_a_bad_choice_is_corrected(top10: tuple[Want, list[Candidate]], bad: str) -> None:
    want, shortlist = top10
    ids = [c.lot.id for c in shortlist]
    wrong = {
        "duplicate": pick(ids[0], ids[0], ids[1]),
        "off_list": pick(ids[0], ids[1], "lot-9999"),
        "two": pick(ids[0], ids[1]),
    }[bad]
    client = FakeClient(
        message(call("choose_lots", wrong)), message(call("choose_lots", pick(*ids[:3])))
    )
    chosen, turn = choose_three(
        client, model="claude-haiku-5-5", want=want, candidates=shortlist, sellers=SELLERS
    )
    assert turn is not None and turn.corrections == 1
    assert [c.lot.id for c in chosen] == ids[:3]


def test_the_schema_only_allows_lots_on_the_shortlist(
    top10: tuple[Want, list[Candidate]],
) -> None:
    want, shortlist = top10
    client = FakeClient(message(call("choose_lots", pick(*[c.lot.id for c in shortlist[:3]]))))
    choose_three(client, model="claude-haiku-5-5", want=want, candidates=shortlist, sellers=SELLERS)
    schema = client.requests[0]["tools"][0]["input_schema"]
    assert sorted(schema["properties"]["lot_ids"]["items"]["enum"]) == sorted(
        c.lot.id for c in shortlist
    )
    assert client.requests[0]["tools"][0]["strict"] is True


def test_three_or_fewer_candidates_need_no_model(top10: tuple[Want, list[Candidate]]) -> None:
    want, shortlist = top10
    client = FakeClient()
    chosen, turn = choose_three(
        client, model="claude-haiku-5-5", want=want, candidates=shortlist[:3], sellers=SELLERS
    )
    assert chosen == shortlist[:3] and turn is None and client.requests == []


def test_live_ralph_picks_three_from_a_real_shortlist(
    top10: tuple[Want, list[Candidate]],
) -> None:
    load_env_file(Path(__file__).parents[1] / ".env")
    want, shortlist = top10
    client = cassette_client(CASSETTES / "ralph_picks_three.jsonl")
    chosen, turn = choose_three(
        client, model="claude-haiku-5-5", want=want, candidates=shortlist, sellers=SELLERS
    )
    assert turn is not None and turn.outcome is Outcome.ACTION
    ids = [c.lot.id for c in chosen]
    assert len(set(ids)) == 3 and set(ids) <= {c.lot.id for c in shortlist}
    print(
        "\n",
        want.text,
        "->",
        [f"{c.lot.title} ({SELLERS[c.lot.seller_id].quality_score})" for c in chosen],
    )
