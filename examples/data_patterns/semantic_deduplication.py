"""Semantic Deduplication.

Before indexing, group chunks that say the same thing and keep one canonical
chunk per group. Two guards stop it from merging things that only *look*
alike: chunks whose numbers differ are never merged, and the merge map is kept
so you can always find what was dropped and why.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

NUMBERS = re.compile(r"\d+(?:[.,]\d+)*")


@dataclass
class Doc:
    id: str
    text: str
    source: str
    updated: date


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / ((sum(x * x for x in a) ** 0.5 or 1.0) * (sum(y * y for y in b) ** 0.5 or 1.0))


def _same_facts(a: str, b: str) -> bool:
    # "Pro costs $49" and "Pro costs $59" embed almost identically. Never merge those.
    return set(NUMBERS.findall(a)) == set(NUMBERS.findall(b))


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def deduplicate(
    docs: list[Doc],
    embed: Callable[[str], list[float]],
    threshold: float = 0.95,
    source_rank: dict[str, int] | None = None,  # lower = more authoritative
) -> tuple[list[Doc], dict[str, str]]:
    """Returns (canonical docs, merged_id -> canonical_id)."""
    vectors = [embed(d.text) for d in docs]
    uf = _UnionFind(len(docs))
    # O(n²) for clarity. At scale, only compare each doc to its ANN neighbours.
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            if _cosine(vectors[i], vectors[j]) >= threshold and _same_facts(docs[i].text, docs[j].text):
                uf.union(i, j)

    clusters: dict[int, list[Doc]] = {}
    for i, doc in enumerate(docs):
        clusters.setdefault(uf.find(i), []).append(doc)

    ranks = source_rank or {}

    def preference(d: Doc):
        return (ranks.get(d.source, 99), -d.updated.toordinal(), -len(d.text))

    canonical, merged = [], {}
    for members in clusters.values():
        keep = min(members, key=preference)
        canonical.append(keep)
        for d in members:
            if d is not keep:
                merged[d.id] = keep.id
    return canonical, merged
