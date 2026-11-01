"""No-Progress Detection.

Watch what an agent loop produces each iteration and say when it has stopped
getting anywhere: the same output again and again (plateau), or bouncing
between a few outputs (oscillation). Return the best iteration seen, which for
an oscillating loop is often not the last one.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable
from dataclasses import dataclass, field

Similarity = Callable[[str, str], float]


def text_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


@dataclass
class ProgressMonitor:
    similarity: Similarity = text_similarity
    same_threshold: float = 0.97  # above this, two outputs count as "the same"
    patience: int = 2  # consecutive stalled iterations before we call it
    max_cycle: int = 3  # detect A-B-A and A-B-C-A cycles
    history: list[str] = field(default_factory=list)
    scores: list[float | None] = field(default_factory=list)
    _plateau: int = 0
    _oscillation: int = 0

    def observe(self, output: str, score: float | None = None) -> str:
        """Returns "improving", "regressing", "plateau" or "oscillating"."""
        prev = self.history[-1] if self.history else None
        self.history.append(output)
        self.scores.append(score)
        if prev is None:
            return "improving"

        if self.similarity(output, prev) >= self.same_threshold:
            self._plateau += 1
            self._oscillation = 0
        else:
            self._plateau = 0
            earlier = self.history[-1 - self.max_cycle : -2]
            if any(self.similarity(output, old) >= self.same_threshold for old in earlier):
                self._oscillation += 1
            else:
                self._oscillation = 0

        if self._plateau >= self.patience:
            return "plateau"
        if self._oscillation >= self.patience:
            return "oscillating"
        if score is not None and self.scores[-2] is not None and score < self.scores[-2]:
            return "regressing"  # worth flagging, not stopping: some paths dip before improving
        return "improving"

    def best(self) -> str:
        scored = [(s, i) for i, s in enumerate(self.scores) if s is not None]
        if scored:
            return self.history[max(scored)[1]]
        return self.history[-1]
