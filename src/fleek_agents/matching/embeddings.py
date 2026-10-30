"""Turning text into vectors, so similar wants and lots end up close together.

LocalEmbedder runs a small open model (bge-small-en-v1.5, 384 numbers per text) on this machine:
no API key, no data sent anywhere. The model (64 MB) downloads once into FLEEK_MODEL_CACHE.
HashingEmbedder is an offline stand-in for tests: it matches shared words only, not meaning.
"""

import hashlib
import os
import re
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

Vectors = NDArray[np.float32]  # one row per text, each row of length 1
MODEL = "BAAI/bge-small-en-v1.5"


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> Vectors: ...


def _unit_rows(vectors: Vectors) -> Vectors:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return (vectors / np.where(norms == 0, 1, norms)).astype(np.float32)


class LocalEmbedder:
    def __init__(self, cache_dir: Path | None = None) -> None:
        from fastembed import TextEmbedding  # imported here: loading it is slow

        cache = cache_dir or Path(os.environ.get("FLEEK_MODEL_CACHE", ".cache/models"))
        self._model = TextEmbedding(MODEL, cache_dir=str(cache))

    def embed(self, texts: list[str]) -> Vectors:
        return _unit_rows(np.array(list(self._model.embed(texts)), dtype=np.float32))


class HashingEmbedder:
    """Each word lands in one of `size` slots. Same words, close vectors. Tests only."""

    def __init__(self, size: int = 256) -> None:
        self._size = size

    def embed(self, texts: list[str]) -> Vectors:
        out = np.zeros((len(texts), self._size), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in re.findall(r"[a-z0-9']+", text.lower()):
                slot = int(hashlib.sha256(word.encode()).hexdigest(), 16) % self._size
                out[row, slot] += 1
        return _unit_rows(out)
