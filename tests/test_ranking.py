import os
from functools import cache

import pytest

from fleek_agents.domain.models import Grade, Want
from fleek_agents.domain.rules import quote
from fleek_agents.market.seed import generate_market
from fleek_agents.matching.embeddings import HashingEmbedder, LocalEmbedder
from fleek_agents.matching.funnel import Candidate
from fleek_agents.matching.ranking import rank, similarity

MARKET = generate_market(seed=2026)
SELLERS = {s.id: s for s in MARKET.sellers}
JEANS = [
    Candidate(lot=lot, quote=quote(lot, SELLERS[lot.seller_id], bundles=1))
    for lot in MARKET.lots
    if lot.category == "jeans" and lot.grade is Grade.A
]
WANT = Want(
    buyer_id="buyer-0001",
    category="jeans",
    grades=(Grade.A,),
    pieces=100,
    text="Levi's 501 jeans, grade A",
)

needs_model = pytest.mark.skipif(
    os.environ.get("FLEEK_SKIP_MODEL") == "1", reason="the 64 MB model isn't available here"
)


@cache
def local() -> LocalEmbedder:
    return LocalEmbedder()


def test_ranking_returns_the_top_ten_best_first() -> None:
    ranked = rank(WANT, JEANS, HashingEmbedder())
    assert len(ranked) == 10
    assert "501" in ranked[0].lot.title  # shares the most words with the want


def test_ranking_is_the_same_every_run() -> None:
    assert rank(WANT, JEANS, HashingEmbedder()) == rank(WANT, JEANS, HashingEmbedder())


def test_no_candidates_means_nothing_to_rank() -> None:
    assert rank(WANT, [], HashingEmbedder()) == []


@needs_model
def test_the_real_model_puts_the_levis_501_lot_first() -> None:
    ranked = rank(WANT, JEANS, local(), top=len(JEANS))
    assert "Levi's 501" in ranked[0].lot.title
    levis = [i for i, c in enumerate(ranked) if c.lot.brand == "Levi's"]
    others = [i for i, c in enumerate(ranked) if c.lot.brand != "Levi's"]
    assert sum(levis) / len(levis) < sum(others) / len(others)  # Levi's rank higher on average


@needs_model
def test_the_real_model_understands_meaning_not_just_shared_words() -> None:
    # "denim" and "jeans" share no words; the hashing stand-in can't see they're related.
    e = local()
    assert similarity("vintage denim", "Levi's jeans", e) > similarity(
        "vintage denim", "Nike t-shirts", e
    )
    h = HashingEmbedder()
    assert similarity("vintage denim", "Levi's jeans", h) == 0.0
