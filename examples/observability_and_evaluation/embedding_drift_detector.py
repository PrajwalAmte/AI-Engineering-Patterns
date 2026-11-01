"""Embedding Drift Detector.

Two numbers, watched over a rolling window of production queries:

1. Centroid shift: how far the average query has moved from the baseline.
   Says "users are asking about different things than before".
2. Alignment: average similarity between each query and its best document.
   Says "retrieval is finding worse matches than before". This is the one
   that predicts bad answers, so it gets the tighter alert.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

Vector = list[float]


def _cosine(a: Vector, b: Vector) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / ((sum(x * x for x in a) ** 0.5 or 1.0) * (sum(y * y for y in b) ** 0.5 or 1.0))


def _centroid(vectors: list[Vector]) -> Vector:
    n = len(vectors)
    return [sum(col) / n for col in zip(*vectors)]


@dataclass
class Baseline:
    centroid: Vector
    alignment: float  # mean best-match similarity on the baseline queries


@dataclass
class DriftReport:
    centroid_shift: float  # 1 - cos(baseline centroid, window centroid)
    alignment: float
    alignment_drop: float
    alerts: list[str] = field(default_factory=list)


@dataclass
class DriftDetector:
    embed: Callable[[str], Vector]
    index: list[Vector]  # sample of document vectors from the live index
    window: int = 500
    max_centroid_shift: float = 0.15
    max_alignment_drop: float = 0.10
    min_samples: int = 50
    baseline: Baseline | None = None
    _recent: deque = field(default_factory=deque)

    def best_match(self, q: Vector) -> float:
        return max((_cosine(q, d) for d in self.index), default=0.0)

    def fit_baseline(self, queries: list[str]) -> Baseline:
        vectors = [self.embed(q) for q in queries]
        self.baseline = Baseline(_centroid(vectors), sum(map(self.best_match, vectors)) / len(vectors))
        self._recent = deque(maxlen=self.window)
        return self.baseline

    def observe(self, query: str) -> None:
        self._recent.append(self.embed(query))

    def report(self) -> DriftReport | None:
        if self.baseline is None or len(self._recent) < self.min_samples:
            return None  # too few queries to say anything; don't alert on noise
        recent = list(self._recent)
        shift = 1 - _cosine(self.baseline.centroid, _centroid(recent))
        alignment = sum(map(self.best_match, recent)) / len(recent)
        drop = self.baseline.alignment - alignment

        alerts = []
        if drop > self.max_alignment_drop:
            alerts.append(f"retrieval alignment fell {drop:.2f} below baseline: check for gaps in the index")
        if shift > self.max_centroid_shift:
            alerts.append(f"query centroid moved {shift:.2f}: users are asking about new things")
        return DriftReport(shift, alignment, drop, alerts)
