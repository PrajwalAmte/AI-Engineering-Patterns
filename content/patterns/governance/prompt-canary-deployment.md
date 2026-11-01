---
title: Prompt Canary Deployment
pillar: governance
status: emerging
tags: [deployment, prompts, rollback, evaluation]
related:
  - Shadow Model Evaluation
  - Prompt Mutation Testing
  - LLM-as-Judge
  - Model Card
example: examples/governance/prompt_canary_deployment.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Ship a prompt change to a small, stable slice of users, compare it with the baseline at each stage, and roll back automatically on any regression.
sidebar:
  order: 2
---

## What It Is

A prompt change is a production deploy and gets the same treatment as code: versioned, rolled out in stages, measured against the current version, and rolled back automatically when something gets worse.

Users are hashed into stable buckets, so each person sees one version throughout the rollout. The new prompt goes to 1% of users, then 5, 25, 50 and 100. At each stage the canary is compared with the baseline on quality (judge scores), safety flags, errors and tokens per request. A breach rolls everyone back.

## The Problem It Solves

Prompts are usually edited in a dashboard or a config file and take effect for everyone at once. "Small" edits ("be more concise", "always cite sources") regularly have large effects. Answers can get longer, refusals rise, JSON breaks for one input shape, or a safety behavior disappears. Offline evals catch some of this. Real traffic catches the rest, and without a canary, all your users are the canary.

## How It Works

<pre class="mermaid">
flowchart LR
    V["New prompt version"] --> O["Offline evals pass?"]
    O -->|"no"| X["Blocked"]
    O -->|"yes"| S1["1%"]
    S1 --> C1{"Metrics vs baseline<br/>(enough samples)"}
    C1 -->|"ok"| S2["5% → 25% → 50% → 100%<br/>(same check each stage)"]
    C1 -->|"breach"| RB["Roll back to 0%"]
    S2 -->|"any breach"| RB
    S2 -->|"all stages ok"| P["Promoted"]
</pre>

1. **Version prompts immutably.** Store them in git or a prompt registry, never as an untracked text field.
2. **Gate on offline evals first** ([Prompt Mutation Testing](../observability-and-evaluation/prompt-mutation-testing.md), regression suites). The canary catches what offline evals miss, not what they would have caught.
3. **Bucket by stable hash** of user ID (salted per rollout), so a user doesn't flip between versions mid-conversation.
4. **Compare against the baseline over the same time window,** not against last week. Traffic changes by hour and by day.
5. **Use different evidence bars.** Safety and error regressions roll back on small samples. Quality regressions need enough data to be real.
6. **Reset the comparison at each stage,** so earlier data doesn't hide a regression that only shows up at higher traffic.

## When to Use It

- User-facing prompts where a regression would be noticed or costly.
- Teams editing prompts frequently, especially non-engineers editing them in a dashboard.
- You can score a sample of responses automatically ([LLM-as-Judge](../observability-and-evaluation/llm-as-judge.md)).

## When NOT to Use It

- **Low traffic.** At a hundred requests a day, the 1% stage takes weeks to reach a meaningful sample. Rely on offline evals and a careful manual review instead.
- **Changes that must reach everyone at once,** such as a legal disclaimer or a safety fix. Ship those directly, and watch them.
- **No automated quality signal.** Without one, the canary can only catch errors and safety flags, which is still worth doing, but call it what it is.

## Trade-offs

- **Slower releases.** A five-stage rollout with minimum samples takes hours to days. That's deliberate.
- **Two versions in production.** Support, debugging and analytics need to know which version a user saw. Log the prompt version on every trace.
- **Metric choice decides what you catch.** Watch tokens per request, not just quality. "Better but 40% longer" is a regression for your bill.

## Failure Modes

**Inconsistent assignment.** Bucketing per request instead of per user means one conversation mixes both prompts, and the metrics compare noise. Hash a stable user or session ID.

**Promoting on too little data.** The canary looks great after 40 requests and someone pushes it to 100%. Enforce minimum samples per stage in the rollout controller, not in a runbook.

**Rolling back the wrong layer.** The prompt rolls back, but the regression came from a model alias that moved underneath it. Pin model versions alongside prompt versions and roll them back together.

## Implementation Example

Salted stable bucketing, a five-stage controller, per-stage baseline comparison of judge score, safety rate, error rate and token growth, immediate rollback on safety or error breaches, and sample-gated rollback on quality.

```bash
cd examples && pytest governance/test_prompt_canary_deployment.py
```

<!-- example: examples/governance/prompt_canary_deployment.py -->
```python
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
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| LaunchDarkly, Statsig, Unleash | Percentage rollouts and stable bucketing; store the prompt version as a flag variation |
| Langfuse, PromptLayer, Braintrust | Prompt registries with versions and labels |
| Argo Rollouts, Flagger | Automated canary analysis when prompts ship with the service |

## Related Patterns

- [Shadow Model Evaluation](../observability-and-evaluation/shadow-model-evaluation.md) is the zero-exposure step before a canary.
- [Prompt Mutation Testing](../observability-and-evaluation/prompt-mutation-testing.md) is the offline gate before either.
- [LLM-as-Judge](../observability-and-evaluation/llm-as-judge.md) provides the quality metric compared at each stage.
- [Model Card](model-card.md) records which prompt version is live and what evals it passed.

## Further Reading

- [Canary Release](https://martinfowler.com/bliki/CanaryRelease.html), Danilo Sato on martinfowler.com
- [Canarying releases](https://sre.google/workbook/canarying-releases/), Google SRE Workbook
- [Patterns for Building LLM-based Systems & Products](https://eugeneyan.com/writing/llm-patterns/), Eugene Yan
