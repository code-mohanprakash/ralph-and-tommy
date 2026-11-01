from sqlalchemy.orm import Session

from fleek_agents.config import MatchingWeights
from fleek_agents.domain.models import Lot, Seller, Want
from fleek_agents.domain.rules import Candidate, quote
from fleek_agents.market.seed import generate_market
from fleek_agents.matching.embeddings import HashingEmbedder
from fleek_agents.matching.explain import why_not
from fleek_agents.matching.score import score
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.market import hard_filter, load_market

MARKET = generate_market(seed=2026)


def test_the_reasons_agree_with_the_sql_filter_for_every_lot_and_buyer() -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        load_market(session, MARKET)
        for want in MARKET.wants[:60]:
            passed = {lot.id for lot in hard_filter(session, want)}
            for lot in MARKET.lots:
                reason = why_not(lot, want, in_stock=lot.available)
                assert (reason is None) == (lot.id in passed), (want.buyer_id, lot.id, reason)


def _lot(n: int, seller: str, title: str, price: int, shipping: int = 300) -> Lot:
    return Lot.model_validate(
        {
            "id": f"lot-{n}",
            "seller_id": seller,
            "title": title,
            "brand": "Levi's",
            "category": "jeans",
            "grade": "A",
            "listing_type": "exact",
            "pieces": 50,
            "available": 1,
            "base_price": price,
            "shipping": shipping,
            "description": "",
        }
    )


SELLERS = {
    "seller-1": Seller(id="seller-1", name="A", country="PK", quality_score=4.8, dispatch_days=2),
    "seller-2": Seller(id="seller-2", name="B", country="PK", quality_score=3.5, dispatch_days=6),
}
WANT = Want(buyer_id="buyer-1", category="jeans", grades=("A",), pieces=50, text="Levi's 501 jeans")


def candidates(*lots: Lot) -> list[Candidate]:
    return [Candidate(lot=lot, quote=quote(lot, SELLERS[lot.seller_id], 1)) for lot in lots]


def test_each_part_is_compared_across_the_candidates() -> None:
    cheap = _lot(1, "seller-2", "Levi's 501 jeans", 1000)
    good = _lot(2, "seller-1", "Levi's 501 jeans", 1300)
    a, b = score(WANT, candidates(cheap, good), SELLERS, HashingEmbedder(), MatchingWeights())
    by_id = {s.lot.id: s for s in (a, b)}
    assert by_id["lot-1"].price == 1.0 and by_id["lot-2"].price < 1.0  # cheapest delivered
    assert by_id["lot-2"].speed == 1.0 and by_id["lot-1"].speed < 1.0  # fastest dispatch
    assert by_id["lot-2"].quality == 4.8 / 5


def test_the_weights_decide_the_order() -> None:
    cheap = _lot(1, "seller-2", "Levi's 501 jeans", 1000)
    good = _lot(2, "seller-1", "Levi's 501 jeans", 1300)
    on_price = MatchingWeights(fit=0, price=100, quality=0, speed=0)
    on_seller = MatchingWeights(fit=0, price=0, quality=50, speed=50)
    lots = candidates(cheap, good)
    assert score(WANT, lots, SELLERS, HashingEmbedder(), on_price)[0].lot.id == "lot-1"
    assert score(WANT, lots, SELLERS, HashingEmbedder(), on_seller)[0].lot.id == "lot-2"


def test_words_that_fit_better_rank_higher_when_all_else_is_equal() -> None:
    fits = _lot(1, "seller-1", "Levi's 501 jeans, grade A", 1200)
    other = _lot(2, "seller-1", "Mixed denim bundle", 1200)
    first = score(WANT, candidates(other, fits), SELLERS, HashingEmbedder(), MatchingWeights())
    assert first[0].lot.id == "lot-1" and first[0].fit > first[1].fit
