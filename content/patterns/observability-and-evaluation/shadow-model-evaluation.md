---
title: Shadow Model Evaluation
pillar: observability-and-evaluation
status: emerging
tags: [evaluation, shadow-traffic, model-comparison, deployment]
related:
  - LLM-as-Judge
  - Prompt Canary Deployment
  - LLM Gateway
  - Model Router
example: examples/observability_and_evaluation/shadow_model_evaluation.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Send a sample of real traffic to a candidate model in the background with tools disabled, judge it against production, and promote only on a clear, significant win.
sidebar:
  order: 5
---

## What It Is

Shadow traffic for models. Production keeps serving users. For a sample of requests, the same input also goes to a candidate model in the background. The candidate's answer is never shown to anyone, and any tools that could have side effects are disabled for it. A judge compares each pair, and the candidate is promoted only when it wins by a margin that is unlikely to be noise.

Shadowing is long-standing practice for backend services. The LLM-specific parts are judging open-ended pairs and keeping a candidate *agent* from acting on the world.

## The Problem It Solves

Offline evals and benchmarks don't look like your traffic. A new model that wins on your 200-case test set can still lose on the long tail of real questions: odd formats, other languages, very long pasted inputs. A canary rollout finds that out by showing a worse model to real users.

Shadowing gets you real traffic with zero user exposure. It costs extra inference, and it can't measure anything that depends on users reacting to the answer.

## How It Works

<pre class="mermaid">
sequenceDiagram
    participant U as User
    participant G as Gateway
    participant P as Production model
    participant Q as Shadow queue (bounded)
    participant C as Candidate (tools off)
    participant J as Judge
    U->>G: request
    G->>P: request
    P-->>G: answer
    G-->>U: answer (always production)
    G--)Q: sampled (prompt, prod answer)
    Q--)C: prompt
    C--)J: candidate answer
    J--)J: prod vs candidate → cand / prod / tie
</pre>

1. **Sample** a fraction of requests (10–20% is common) into a *bounded* queue. When it's full, drop shadow work. Never slow production to keep up.
2. **Run the candidate with side effects off.** Tools that write, send or charge are disabled or mocked. Enforce this in code, not in the prompt.
3. **Judge each pair** with a pairwise judge run in both orders ([LLM-as-Judge](llm-as-judge.md)). Record shadow errors separately. They're part of the result.
4. **Decide on statistics, not vibes.** Promote only when a pessimistic estimate of the candidate's win rate (for example, the Wilson lower bound) is above 50% over enough decided comparisons. Reject when the optimistic estimate is below 50%. Otherwise the models are equivalent, so choose on cost and latency.
5. **Slice the results** by feature or query type before promoting. A candidate can win overall and lose badly on one segment.

## When to Use It

- Model upgrades, provider switches, fine-tuned replacements and major prompt rewrites in user-facing systems.
- Enough traffic to accumulate a few hundred decided comparisons in reasonable time.
- When you want a "no regressions on real traffic" check before a canary.

## When NOT to Use It

- **Requests whose value is the side effect.** If the agent's job is to file the ticket, a tools-off shadow can't show whether it would have filed it correctly. Use a sandboxed environment with recorded tool responses instead.
- **Very low traffic.** You'd wait weeks for significance. Use a curated offline set and a careful canary.
- **Data that can't go to the candidate's endpoint,** such as a different provider or region with different data terms.

## Trade-offs

- **Cost.** You pay for the candidate *and* the judge on every sampled request. Sampling is the dial.
- **Users never see the candidate.** Follow-up questions, satisfaction and task completion can't be measured in shadow. Shadowing de-risks a canary. It doesn't replace one.
- **The judge decides.** A judge biased toward longer answers will promote the more verbose model. Calibrate it first.

## Failure Modes

**Side effects leak.** The candidate agent sends a real email or writes to a production table. Disabling tools has to be structural: give the shadow path no credentials, read-only replicas and stubbed tools.

**The shadow slows production.** The shadow call is made inline "just for now", and p95 doubles. Make it asynchronous with a bounded queue and load-shedding, as the example does.

**Declaring a winner too early.** The candidate is up 60–40 after 100 comparisons, and someone promotes it. Set the minimum sample size and the decision rule before looking at the results.

## Implementation Example

A production path that can't be affected by the shadow, sampling into a bounded queue with load-shedding, tools disabled for the candidate, error counting, and a promote / reject / no-difference decision based on Wilson bounds. The tests cover each guarantee, including a candidate that crashes on every call.

```bash
cd examples && pytest observability_and_evaluation/test_shadow_model_evaluation.py
```

<!-- example: examples/observability_and_evaluation/shadow_model_evaluation.py -->
```python
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
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Your LLM gateway (LiteLLM, Portkey, Kong, …) | Mirror or duplicate requests; often the simplest place to add shadowing |
| Istio / Envoy traffic mirroring | Mirror at the mesh layer for self-hosted models |
| Braintrust, LangSmith, Langfuse | Store pairs and run pairwise judges as experiments |
| Seldon Core, KServe | Shadow deployments for self-hosted model servers |

## Related Patterns

- [LLM-as-Judge](llm-as-judge.md) supplies the pairwise verdicts this pattern relies on.
- [Prompt Canary Deployment](../governance/prompt-canary-deployment.md) is the next step: a small share of real users, after shadowing passes.
- [LLM Gateway](../inference-and-serving/llm-gateway.md) is where duplication and sampling naturally live.
- [Model Router](../inference-and-serving/model-router.md): shadow a cheaper model on one tier to see whether you can move that tier down.

## Further Reading

- [Istio traffic mirroring](https://istio.io/latest/docs/tasks/traffic-management/mirroring/)
- [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685), Zheng et al., 2023. On pairwise judgments and their biases.
