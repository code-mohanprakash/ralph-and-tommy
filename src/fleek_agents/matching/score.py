"""Ranking the lots that could work, on public facts, with the reasons kept for the screen.

Each part is a number from 0 to 1, compared across this buyer's candidates:
- fit: how close the lot's words are to the buyer's, against the other candidates. Raw cosine
  similarities from an embedding model bunch together (0.79 against 0.83 for "505" and "501"
  when the buyer wrote "501"), so the closest candidate scores 1 and the others lose ground by
  how far they trail, over a spread of at least FIT_SPREAD so tiny differences can't swing it;
- price: the cheapest delivered price per piece scores 1, others cheapest / theirs;
- quality: the seller's public rating out of 5;
- speed: the fastest dispatch scores 1, others fastest / theirs.

The total is the weighted sum (market.toml [matching]). B2B buyers care about price, seller
reliability and delivery, not only words: Fleek's own reviews complain about quality more than
anything (reports/Fleek revenue and negotiation modes.md). No secret is an input, so the order
tells nobody anything the vault didn't already say.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from fleek_agents.config import MatchingWeights
from fleek_agents.domain.models import Lot, Seller, Want
from fleek_agents.domain.rules import Candidate
from fleek_agents.matching.embeddings import Embedder

FIT_SPREAD = 0.1  # cosine differences smaller than this count for less than the whole fit weight


@dataclass(frozen=True)
class Scored:
    candidate: Candidate
    total: float
    fit: float  # 0 to 1, against the other candidates
    price: float
    quality: float
    speed: float

    @property
    def lot(self) -> Lot:
        return self.candidate.lot


def lot_words(lot: Lot) -> str:
    return f"{lot.title} {lot.brand} {lot.category} grade {lot.grade}"


def score(
    want: Want,
    candidates: list[Candidate],
    sellers: Mapping[str, Seller],
    embedder: Embedder,
    weights: MatchingWeights,
) -> list[Scored]:
    """Every candidate, best first. Ties go to the lower lot id, so the order is stable."""
    if not candidates:
        return []
    vectors = embedder.embed([want.text] + [lot_words(c.lot) for c in candidates])
    raw = [max(0.0, float(x)) for x in vectors[1:] @ vectors[0]]
    best_fit, worst_fit = max(raw), min(raw)
    spread = max(best_fit - worst_fit, FIT_SPREAD)
    fits = [max(0.0, 1 - (best_fit - r) / spread) for r in raw]
    delivered = [c.quote.base_price.value + c.quote.shipping.value for c in candidates]
    days = [max(1, sellers[c.lot.seller_id].dispatch_days) for c in candidates]
    cheapest, fastest = min(delivered), min(days)
    w = weights
    whole = w.fit + w.price + w.quality + w.speed
    out = []
    for i, c in enumerate(candidates):
        fit = fits[i]
        price = cheapest / delivered[i]
        quality = sellers[c.lot.seller_id].quality_score / 5
        speed = fastest / days[i]
        total = (w.fit * fit + w.price * price + w.quality * quality + w.speed * speed) / whole
        out.append(Scored(c, total, fit, price, quality, speed))
    return sorted(out, key=lambda s: (-s.total, s.lot.id))
