"""Semantic Caching.

Serve a cached answer when a new query means the same thing as an old one.
The similarity threshold is only half the safety story: entries are also
scoped (same system prompt, same tenant), expire, and can be invalidated when
the documents they were built from change.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field

Embed = Callable[[str], list[float]]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


@dataclass
class Entry:
    query: str
    vector: list[float]
    answer: str
    scope: str
    sources: frozenset[str]
    expires_at: float


@dataclass
class SemanticCache:
    embed: Embed
    threshold: float = 0.92  # tune per workload against labelled near-duplicate pairs
    ttl_s: float = 3600.0
    max_entries: int = 10_000
    clock: Callable[[], float] = time.monotonic
    entries: list[Entry] = field(default_factory=list)
    hits: int = 0
    misses: int = 0

    @staticmethod
    def scope_key(system_prompt: str, tenant: str) -> str:
        # Two identical questions under different system prompts are different questions.
        return hashlib.sha256(f"{tenant}\x00{system_prompt}".encode()).hexdigest()[:16]

    def lookup(self, query: str, scope: str) -> str | None:
        now = self.clock()
        self.entries = [e for e in self.entries if e.expires_at > now]
        vector = self.embed(query)
        best, best_sim = None, self.threshold
        for entry in self.entries:
            if entry.scope != scope:
                continue
            sim = _cosine(vector, entry.vector)
            if sim >= best_sim:
                best, best_sim = entry, sim
        if best is None:
            self.misses += 1
            return None
        self.hits += 1
        return best.answer

    def store(self, query: str, answer: str, scope: str, sources: set[str] = frozenset()) -> None:
        if len(self.entries) >= self.max_entries:
            self.entries.pop(0)  # oldest first; good enough when TTLs do most of the eviction
        self.entries.append(
            Entry(query, self.embed(query), answer, scope, frozenset(sources), self.clock() + self.ttl_s)
        )

    def invalidate_source(self, source_id: str) -> int:
        """Call from your ingestion pipeline when a document changes."""
        before = len(self.entries)
        self.entries = [e for e in self.entries if source_id not in e.sources]
        return before - len(self.entries)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


def cached_complete(
    cache: SemanticCache,
    llm: Callable[[str], str],
    query: str,
    system_prompt: str,
    tenant: str,
    cacheable: Callable[[str], bool] = lambda answer: bool(answer.strip()),
) -> tuple[str, bool]:
    """Returns (answer, was_cache_hit). Only answers that pass `cacheable` are stored."""
    scope = cache.scope_key(system_prompt, tenant)
    hit = cache.lookup(query, scope)
    if hit is not None:
        return hit, True
    answer = llm(f"{system_prompt}\n\n{query}")
    if cacheable(answer):
        cache.store(query, answer, scope)
    return answer, False
