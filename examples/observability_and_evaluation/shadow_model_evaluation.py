"""Shadow Model Evaluation.

Serve production as usual. For a sample of requests, also send the request to
a candidate model in the background with side-effecting tools disabled, then
have a judge compare the two answers. The candidate is promoted only when it
wins clearly over enough comparisons, not after the first good afternoon.
"""

from __future__ import annotations

import math
import queue
import random
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

Model = Callable[[str, bool], str]  # (prompt, tools_enabled) -> answer
PairJudge = Callable[[str, str, str], str]  # (prompt, production, candidate) -> "prod" | "cand" | "tie"


@dataclass
class Tally:
    cand: int = 0
    prod: int = 0
    tie: int = 0
    errors: int = 0

    @property
    def decided(self) -> int:
        return self.cand + self.prod


def wilson_lower_bound(wins: int, n: int, z: float = 1.96) -> float:
    """Pessimistic estimate of the true win rate (95% by default)."""
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / denom


@dataclass
class ShadowEvaluator:
    production: Model
    candidate: Model
    judge: PairJudge
    sample_rate: float = 0.2
    max_queue: int = 1000
    rng: random.Random = field(default_factory=random.Random)
    tally: Tally = field(default_factory=Tally)
    dropped: int = 0

    def __post_init__(self):
        self._queue: queue.Queue = queue.Queue(maxsize=self.max_queue)
        self._lock = threading.Lock()

    def handle(self, prompt: str) -> str:
        """The production path. Nothing the shadow does can slow or break it."""
        answer = self.production(prompt, True)
        if self.rng.random() < self.sample_rate:
            try:
                self._queue.put_nowait((prompt, answer))
            except queue.Full:
                self.dropped += 1  # shed shadow work, never production work
        return answer

    def drain(self) -> None:
        """Run by a background worker; called directly in tests."""
        while True:
            try:
                prompt, prod_answer = self._queue.get_nowait()
            except queue.Empty:
                return
            try:
                cand_answer = self.candidate(prompt, False)  # tools off: no emails, no writes
                verdict = self.judge(prompt, prod_answer, cand_answer)
            except Exception:
                with self._lock:
                    self.tally.errors += 1
                continue
            with self._lock:
                setattr(self.tally, verdict, getattr(self.tally, verdict) + 1)

    def decision(self, min_decided: int = 200, promote_above: float = 0.5) -> str:
        t = self.tally
        if t.decided < min_decided:
            return f"keep shadowing ({t.decided}/{min_decided} decided comparisons)"
        lower = wilson_lower_bound(t.cand, t.decided)
        upper = 1 - wilson_lower_bound(t.prod, t.decided)
        if lower > promote_above:
            return f"promote: candidate wins {t.cand}/{t.decided}, lower bound {lower:.2f}"
        if upper < promote_above:
            return f"reject: candidate wins {t.cand}/{t.decided}, upper bound {upper:.2f}"
        return "no clear difference: decide on cost and latency"
