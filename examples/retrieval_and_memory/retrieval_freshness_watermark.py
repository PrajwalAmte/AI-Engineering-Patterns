"""Retrieval Freshness Watermark.

Every chunk carries the date its content was effective, not the date it was
indexed. At query time: superseded versions are dropped, freshness is blended
into the score only for time-sensitive queries, and each chunk goes into the
prompt with an "as of" line so the model can say how current its answer is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# How long until a chunk is "half as fresh", by content type. These are
# starting points to argue about, not constants of nature.
HALF_LIFE_DAYS = {"pricing": 90, "news": 14, "policy": 365, "reference": 3650}
FRESHNESS_FLOOR = 0.2  # old-but-unrevoked content still competes
TIME_SENSITIVE = re.compile(r"\b(current|currently|latest|now|today|this (week|month|year)|price|pricing|cost)\b", re.I)


@dataclass
class Chunk:
    doc_key: str  # stable id of the logical document, shared across versions
    text: str
    effective: date  # when this content became true, NOT when it was indexed
    content_type: str = "reference"
    expired: bool = False  # explicitly revoked: never served


def freshness(chunk: Chunk, today: date) -> float:
    age = max((today - chunk.effective).days, 0)
    half_life = HALF_LIFE_DAYS.get(chunk.content_type, 365)
    return max(FRESHNESS_FLOOR, 0.5 ** (age / half_life))


def rank(
    query: str,
    candidates: list[tuple[Chunk, float]],  # (chunk, similarity) from your retriever
    today: date,
    k: int = 4,
) -> list[tuple[Chunk, float]]:
    # 1. Revoked content is gone; of several versions of one document, keep the newest.
    newest: dict[str, tuple[Chunk, float]] = {}
    for chunk, sim in candidates:
        if chunk.expired:
            continue
        held = newest.get(chunk.doc_key)
        if held is None or chunk.effective > held[0].effective:
            newest[chunk.doc_key] = (chunk, sim)

    # 2. Only let age move the ranking when the question is about the present.
    alpha = 0.6 if TIME_SENSITIVE.search(query) else 0.95
    scored = [(c, alpha * sim + (1 - alpha) * freshness(c, today)) for c, sim in newest.values()]
    return sorted(scored, key=lambda pair: -pair[1])[:k]


def build_context(ranked: list[tuple[Chunk, float]], today: date) -> str:
    lines = [
        f"Today is {today.isoformat()}. Each source shows the date it was effective.",
        "If sources conflict, prefer the more recent one. If the newest relevant source is old,",
        "say how old it is instead of presenting it as current.",
        "",
    ]
    for i, (chunk, _) in enumerate(ranked, start=1):
        age = (today - chunk.effective).days
        lines.append(f"[{i}] (as of {chunk.effective.isoformat()}, {age} days old) {chunk.text}")
    return "\n".join(lines)
