"""Retrieval Quality Gate.

Score every retrieved chunk for whether it helps answer *this* query, drop
the ones that don't, and if too little survives, say so instead of letting the
model improvise from noise.

`score(query, chunk) -> float in [0, 1]` is the pluggable part: a
cross-encoder or reranker API in production, a cheap lexical scorer here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

Scorer = Callable[[str, str], float]

_STOP = set("a an the is are was what how do does to of in on for and or my i it".split())


def lexical_score(query: str, chunk: str) -> float:
    q = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in _STOP}
    c = set(re.findall(r"[a-z0-9]+", chunk.lower()))
    return len(q & c) / len(q) if q else 0.0


@dataclass
class GateResult:
    decision: str  # "answer" | "abstain"
    kept: list[tuple[str, float]] = field(default_factory=list)
    dropped: list[tuple[str, float]] = field(default_factory=list)


def gate(
    query: str,
    chunks: list[str],
    score: Scorer = lexical_score,
    threshold: float = 0.5,
    relative_cutoff: float = 0.6,  # also drop anything far below the best chunk
    min_kept: int = 1,
    max_kept: int = 5,
) -> GateResult:
    scored = sorted(((c, score(query, c)) for c in chunks), key=lambda p: -p[1])
    best = scored[0][1] if scored else 0.0
    floor = max(threshold, best * relative_cutoff)

    kept = [p for p in scored if p[1] >= floor][:max_kept]
    dropped = [p for p in scored if p not in kept]
    # Log `dropped` with its scores: reviewing what the gate threw away is how
    # you find a threshold that's too strict.
    return GateResult("answer" if len(kept) >= min_kept else "abstain", kept, dropped)


def answer(query: str, chunks: list[str], llm: Callable[[str], str], **gate_kwargs) -> str:
    result = gate(query, chunks, **gate_kwargs)
    if result.decision == "abstain":
        return "I couldn't find anything in the knowledge base that answers that."
    context = "\n\n".join(c for c, _ in result.kept)
    return llm(f"Answer using only this context:\n{context}\n\nQuestion: {query}")
