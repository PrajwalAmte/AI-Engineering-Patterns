"""Hybrid Search: BM25 + dense retrieval, merged with Reciprocal Rank Fusion.

BM25 finds the exact error code; embeddings find the paraphrase. RRF merges
the two rankings without having to make their scores comparable.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

Embed = Callable[[str], list[float]]
_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-_.]*", re.I)


def tokenize(text: str) -> list[str]:
    # Keep identifiers like "E-4012" and "v2.3.1" whole; they are why BM25 is here.
    return [t.lower().strip(".") for t in _TOKEN.findall(text)]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [tokenize(d) for d in docs]
        self.avg_len = sum(map(len, self.docs)) / max(len(self.docs), 1)
        df = Counter(term for doc in self.docs for term in set(doc))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        out = []
        for doc in self.docs:
            tf = Counter(doc)
            norm = self.k1 * (1 - self.b + self.b * len(doc) / self.avg_len)
            out.append(sum(self.idf.get(t, 0.0) * tf[t] * (self.k1 + 1) / (tf[t] + norm) for t in terms if tf[t]))
        return out


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / ((sum(x * x for x in a) ** 0.5 or 1.0) * (sum(y * y for y in b) ** 0.5 or 1.0))


def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion: score(d) = sum over lists of 1 / (k + rank)."""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return fused


@dataclass
class Hit:
    doc_id: int
    text: str
    score: float
    sparse_rank: int | None
    dense_rank: int | None


class HybridIndex:
    def __init__(self, docs: list[str], embed: Embed, min_dense_sim: float = 0.1):
        self.docs = docs
        self.embed = embed
        self.min_dense_sim = min_dense_sim
        self.bm25 = BM25(docs)  # in production: your keyword index (Elasticsearch, Postgres FTS, ...)
        self.vectors = [embed(d) for d in docs]  # in production: your vector index

    def search(self, query: str, k: int = 5, candidates: int = 20) -> list[Hit]:
        sparse = self.bm25.scores(query)
        sparse_rank = [i for i in sorted(range(len(sparse)), key=lambda i: -sparse[i]) if sparse[i] > 0][:candidates]

        qv = self.embed(query)
        sims = [_cosine(qv, v) for v in self.vectors]
        # A per-method floor keeps one retriever's junk from diluting the fusion.
        dense_rank = [
            i for i in sorted(range(len(sims)), key=lambda i: -sims[i]) if sims[i] >= self.min_dense_sim
        ][:candidates]

        fused = rrf([sparse_rank, dense_rank])
        top = sorted(fused, key=lambda i: -fused[i])[:k]
        return [
            Hit(
                i,
                self.docs[i],
                fused[i],
                sparse_rank.index(i) + 1 if i in sparse_rank else None,
                dense_rank.index(i) + 1 if i in dense_rank else None,
            )
            for i in top
        ]
