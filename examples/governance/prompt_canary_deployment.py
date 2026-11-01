"""Prompt Canary Deployment.

A prompt change is a deploy. Users are hashed into a stable bucket, a small
share sees the new version, and the rollout advances through stages only if
the canary's metrics stay within tolerance of the baseline. Any guardrail
breach rolls back automatically.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

STAGES = [1, 5, 25, 50, 100]  # percent of users on the new version


def bucket(user_id: str, salt: str) -> int:
    """Stable 0-99 bucket. Same user, same salt -> same version for the whole rollout."""
    digest = hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()
    return int(digest[:8], 16) % 100


@dataclass
class Metrics:
    n: int = 0
    judge_score_sum: float = 0.0
    safety_flags: int = 0
    errors: int = 0
    tokens_sum: int = 0

    def add(self, judge_score: float, safety_flag: bool, error: bool, tokens: int) -> None:
        self.n += 1
        self.judge_score_sum += judge_score
        self.safety_flags += safety_flag
        self.errors += error
        self.tokens_sum += tokens

    def rate(self, attr: str) -> float:
        return getattr(self, attr) / self.n if self.n else 0.0

    @property
    def judge_mean(self) -> float:
        return self.judge_score_sum / self.n if self.n else 0.0


@dataclass
class Tolerance:
    max_judge_drop: float = 0.1  # on a 1-4 rubric
    max_safety_rate_increase: float = 0.002
    max_error_rate_increase: float = 0.01
    max_token_increase: float = 0.15  # relative
    min_samples: int = 300  # per arm, per stage


@dataclass
class Rollout:
    baseline_version: str
    candidate_version: str
    tolerance: Tolerance = field(default_factory=Tolerance)
    stage: int = 0
    state: str = "rolling"  # rolling | promoted | rolled_back
    baseline: Metrics = field(default_factory=Metrics)
    canary: Metrics = field(default_factory=Metrics)
    history: list[str] = field(default_factory=list)

    @property
    def percent(self) -> int:
        if self.state == "rolled_back":
            return 0
        return 100 if self.state == "promoted" else STAGES[self.stage]

    def version_for(self, user_id: str) -> str:
        on_canary = bucket(user_id, self.candidate_version) < self.percent
        return self.candidate_version if on_canary else self.baseline_version

    def breaches(self) -> list[str]:
        t, b, c = self.tolerance, self.baseline, self.canary
        out = []
        if b.judge_mean - c.judge_mean > t.max_judge_drop:
            out.append(f"judge score {c.judge_mean:.2f} vs {b.judge_mean:.2f}")
        if c.rate("safety_flags") - b.rate("safety_flags") > t.max_safety_rate_increase:
            out.append("safety flag rate up")
        if c.rate("errors") - b.rate("errors") > t.max_error_rate_increase:
            out.append("error rate up")
        if b.n and c.n and (c.tokens_sum / c.n) > (b.tokens_sum / b.n) * (1 + t.max_token_increase):
            out.append("tokens per request up")
        return out

    def evaluate(self) -> str:
        """Call on a schedule (e.g. every 15 minutes)."""
        if self.state != "rolling":
            return self.state
        problems = self.breaches()
        # Safety and errors can roll back on small samples; quality needs enough data.
        urgent = [p for p in problems if "safety" in p or "error" in p]
        if urgent or (problems and min(self.baseline.n, self.canary.n) >= self.tolerance.min_samples):
            self.state = "rolled_back"
            self.history.append(f"rolled back at {STAGES[self.stage]}%: {', '.join(problems)}")
            return self.state
        if min(self.baseline.n, self.canary.n) < self.tolerance.min_samples:
            return "waiting for data"
        if self.stage == len(STAGES) - 1:
            self.state = "promoted"
        else:
            self.stage += 1
            self.baseline, self.canary = Metrics(), Metrics()  # fresh comparison per stage
        self.history.append(f"advanced to {self.percent}%")
        return self.state
