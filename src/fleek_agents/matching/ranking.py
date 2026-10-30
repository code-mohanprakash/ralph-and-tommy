"""Step 3 of the funnel: rank the lots that could work by how well they match the want's words.

Plain NumPy: with every row of length 1, cosine similarity is one matrix product. No vector
database (decision 002).
"""

import numpy as np

from fleek_agents.domain.models import Want
from fleek_agents.matching.embeddings import Embedder
from fleek_agents.matching.funnel import Candidate

TOP = 10


def rank(
    want: Want, candidates: list[Candidate], embedder: Embedder, top: int = TOP
) -> list[Candidate]:
    """The `top` candidates most similar to the buyer's words, best first. Ties go to the lower
    lot id, so the order is the same every run."""
    if not candidates:
        return []
    want_vector = embedder.embed([want.text])[0]
    lot_vectors = embedder.embed([c.lot.title for c in candidates])
    scores = lot_vectors @ want_vector
    order = sorted(range(len(candidates)), key=lambda i: (-float(scores[i]), candidates[i].lot.id))
    return [candidates[i] for i in order[:top]]


def similarity(a: str, b: str, embedder: Embedder) -> float:
    vectors = embedder.embed([a, b])
    return float(np.dot(vectors[0], vectors[1]))
