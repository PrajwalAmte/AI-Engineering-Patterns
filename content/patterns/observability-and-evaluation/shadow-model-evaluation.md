---
title: Shadow Model Evaluation
pillar: observability-and-evaluation
status: emerging
tags: [evaluation, shadow-traffic, model-comparison, deployment, quality]
related:
  - LLM-as-Judge
  - Span-Level Tracing
  - Prompt Canary Deployment
  - Model Router
contributors: ["@PrajwalAmte"]
last_updated: "2026-07"
description: Route production traffic to a shadow model in parallel, comparing outputs without serving them to users to safely validate new models before any real-user exposure.
sidebar:
  order: 5
---

## What It Is

Shadow Model Evaluation duplicates live production requests to a candidate model running in parallel, collects both the production response (served to users) and the shadow response (never shown), then automatically compares them. This gives you a continuous, real-traffic quality comparison between the current production model and any candidate—new model version, fine-tuned variant, or prompt change—without any user-facing risk. It is the LLM equivalent of shadow mode traffic in distributed systems.

## The Problem It Solves

Validating a new model or prompt against real production traffic is the hardest problem in LLM deployment:

- **Benchmark divergence**: Offline benchmarks (MMLU, HumanEval) do not reflect your actual query distribution. A model that scores 5% better on benchmarks can perform worse on your specific workload.
- **Canary risk**: Even a 1% canary rollout exposes real users to regressions before you have measured the full impact.
- **Sample bias in staging**: Manually constructed test sets do not capture the long tail of production queries—the edge cases that expose model weaknesses.
- **Latency unknowns**: A new model may be slower at your actual request rate even if it is faster in isolation.

Shadow evaluation gives you real query distribution, zero user exposure, and continuous quality metrics before any traffic decision.

## How It Works

<pre class="mermaid">
sequenceDiagram
    participant User
    participant Gateway
    participant Production as Production Model
    participant Shadow as Shadow Model
    participant Evaluator as Async Evaluator
    participant Dashboard

    User->>Gateway: Request
    Gateway->>Production: Forward request
    Gateway-->>Shadow: Duplicate request (async)
    Production-->>Gateway: Response (served)
    Gateway-->>User: Return production response
    Shadow-->>Evaluator: Shadow response (not served)
    Production-->>Evaluator: Production response copy
    Evaluator->>Evaluator: LLM-as-Judge comparison
    Evaluator->>Dashboard: win/loss/tie + latency delta
</pre>

1. **Request duplication**: LLM gateway intercepts each production request and fires an identical asynchronous request to the shadow model. This must not block the production response path.
2. **Serve production only**: Return the production model response to the user. The shadow response is never shown.
3. **Async collection**: Shadow response and production response are written to an evaluation queue (message bus or database).
4. **Automated comparison**: An asynchronous evaluator runs LLM-as-Judge comparisons on each (production, shadow) pair: shadow win / production win / tie, using a task-specific rubric.
5. **Aggregate metrics**: Compute shadow win rate, latency percentiles (p50, p95), cost per request, and quality scores by query category.
6. **Traffic decision**: If shadow win rate exceeds threshold (e.g., 55% after N requests) with statistical significance, promote shadow to production. Otherwise, reject.

**Critical constraint**: Shadow requests must be isolated. They must not affect production state, must not be visible in production logs as user traffic, and must not trigger downstream side effects (emails, writes, external API calls).

## When to Use It

- Before any model upgrade or version change in a user-facing system
- Evaluating fine-tuned models against the base model on real workload
- Comparing prompt variants at scale without A/B test user risk
- Continuous model monitoring: run shadow evaluation permanently to detect provider regressions
- When your query distribution is too varied to cover with a manual test set

## When NOT to Use It

- Low-traffic systems (fewer than 100 requests/day) where shadow data accumulates too slowly for statistical significance
- Requests with side effects that cannot be isolated (tool calls that write to databases, send emails)
- Real-time streaming responses where duplicating the connection is architecturally complex
- When shadow model cost is prohibitive at production scale (shadow adds approximately 100% inference cost)
- Requests containing sensitive user data that must not be transmitted to a different model endpoint

## Trade-offs

1. **Inference cost doubles** — Every production request generates one shadow request. If your production LLM costs $1,000/month, shadow evaluation adds $1,000/month minimum. Use request sampling (e.g., shadow 20% of traffic) to reduce cost at the expense of slower signal accumulation.

2. **Shadow queue backpressure** — Production path is unaffected since shadow is async. However, if the shadow model is significantly slower, the evaluation queue backs up. Use a bounded queue with backpressure to prevent memory exhaustion.

3. **Judge quality determines decision quality** — The LLM-as-Judge comparison drives your promotion decision. A miscalibrated judge (one that favors longer responses or newer phrasing styles) produces misleading win rates. Validate judge agreement with human labels on a sample before trusting automated decisions.

4. **Statistical significance requires patience** — At 20% shadow rate, getting 1,000 evaluated pairs requires 5,000 production requests. For low-traffic systems, shadow evaluation takes days to weeks to produce actionable signal.

## Failure Modes

### Side Effect Leakage
**Trigger**: Shadow request triggers a real tool call (web search, database write, email send) that affects the production system or external services.
**Symptom**: Duplicate emails sent to users, corrupted database state, unexpected API charges from tool executions.
**Mitigation**: Shadow requests must run in a sandboxed context: mock all tool implementations to no-ops, route to read-only database replicas, disable webhook callbacks. Enforce sandbox via middleware, not trust in the caller.

### Queue Backlog Under Shadow Model Latency
**Trigger**: Shadow model is 3x slower than production. Shadow responses pile up in the evaluation queue faster than the evaluator processes them.
**Symptom**: Evaluation queue grows unbounded, consuming memory. Old shadow results eventually dropped or evaluated hours after the production request, making latency comparison meaningless.
**Mitigation**: Set maximum queue depth with a circuit breaker: if queue exceeds N items, drop new shadow requests until queue drains. Add queue depth as a monitoring metric with alert threshold.

### Judge Preference Drift
**Trigger**: LLM-as-Judge has a systematic bias favoring responses with more structured formatting (bullet points, headers) regardless of accuracy. Shadow model uses more formatting.
**Symptom**: Shadow model wins 65% of comparisons even though human raters prefer production model 60% of the time.
**Mitigation**: Regularly validate judge scores against human-labeled pairs. Use multiple judges with different models and take majority vote. Include accuracy-focused rubric criteria, not just fluency.

### Sampling Bias in Shadow Selection
**Trigger**: Shadow traffic is sampled by filtering to only "interesting" queries (e.g., those containing certain keywords). The sample is not representative.
**Symptom**: Shadow model performs well on sampled queries but regresses on unsampled query types. Promotion decision is based on biased data.
**Mitigation**: Use uniform random sampling. If stratified sampling is needed for cost reasons, ensure all query categories are represented proportionally.

## Implementation Example

```python
import asyncio
import uuid
import json
from dataclasses import dataclass
from typing import Optional, Callable

@dataclass
class ShadowEvaluationRecord:
    request_id: str
    user_query: str
    production_response: str
    shadow_response: str
    production_latency_ms: float
    shadow_latency_ms: float
    judge_verdict: Optional[str] = None  # "production_wins" | "shadow_wins" | "tie"
    judge_reasoning: Optional[str] = None

class ShadowModelEvaluator:
    """
    Routes requests to production model and optionally shadows to candidate model.
    All shadow activity is async and never blocks production.
    """

    def __init__(
        self,
        production_model: str,
        shadow_model: str,
        shadow_rate: float = 0.2,
        judge_model: str = "gpt-4o-mini"
    ):
        self.production_model = production_model
        self.shadow_model = shadow_model
        self.shadow_rate = shadow_rate
        self.judge_model = judge_model
        self.evaluation_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

    async def complete(self, query: str, llm_call: Callable, **kwargs) -> str:
        import random, time

        request_id = str(uuid.uuid4())
        prod_start = time.monotonic()
        production_response = await llm_call(
            model=self.production_model, prompt=query, **kwargs
        )
        prod_latency = (time.monotonic() - prod_start) * 1000

        if random.random() < self.shadow_rate:
            asyncio.create_task(
                self._shadow_and_enqueue(
                    request_id, query, production_response, prod_latency, llm_call, **kwargs
                )
            )

        return production_response

    async def _shadow_and_enqueue(
        self, request_id, query, production_response, prod_latency, llm_call, **kwargs
    ):
        import time
        try:
            shadow_start = time.monotonic()
            shadow_response = await llm_call(
                model=self.shadow_model, prompt=query, **kwargs
            )
            shadow_latency = (time.monotonic() - shadow_start) * 1000

            record = ShadowEvaluationRecord(
                request_id=request_id,
                user_query=query,
                production_response=production_response,
                shadow_response=shadow_response,
                production_latency_ms=prod_latency,
                shadow_latency_ms=shadow_latency
            )

            if not self.evaluation_queue.full():
                await self.evaluation_queue.put(record)
        except Exception:
            pass  # Never let shadow failure affect production

    async def run_evaluator(self, llm_call: Callable) -> None:
        """Background task: drain queue and run LLM-as-Judge comparisons"""
        while True:
            record: ShadowEvaluationRecord = await self.evaluation_queue.get()

            judge_prompt = f"""You are evaluating two AI responses to the same query.

Query: {record.user_query}

Response A (Production): {record.production_response}

Response B (Shadow/Candidate): {record.shadow_response}

Which response is better? Consider accuracy, completeness, clarity, and helpfulness.
Respond with JSON only:
{{"verdict": "production_wins or shadow_wins or tie", "reasoning": "one sentence"}}"""

            try:
                result = await llm_call(model=self.judge_model, prompt=judge_prompt)
                parsed = json.loads(result)
                record.judge_verdict = parsed["verdict"]
                record.judge_reasoning = parsed["reasoning"]

                print(
                    f"shadow_eval | id={record.request_id} verdict={record.judge_verdict} "
                    f"prod={record.production_latency_ms:.0f}ms "
                    f"shadow={record.shadow_latency_ms:.0f}ms"
                )
            except Exception:
                pass
```

## Tool Landscape

| Tool | Type | Notes |
|------|------|-------|
| LiteLLM | Open-source proxy | Supports fallback routing; can be extended for shadow duplication |
| Langfuse | Open-source observability | Can log both production and shadow traces for comparison |
| Braintrust | Managed evaluation | Supports A/B evaluation and model comparison pipelines |
| Portkey | Managed gateway | Gateway-level traffic duplication and response logging |
| Kafka / SQS | Message bus | Use as evaluation queue for high-volume shadow traffic |
| Custom implementation | DIY | Required for full control over sandbox isolation and evaluation rubric |

## Related Patterns

- **[LLM-as-Judge](llm-as-judge.md)** — Shadow Model Evaluation uses LLM-as-Judge as its core comparison mechanism; judge quality determines the reliability of every promotion decision.
- **[Prompt Canary Deployment](../governance/prompt-canary-deployment.md)** — Shadow evaluation precedes canary: validate silently first, then expose a small fraction of real users.
- **[Model Router](../inference-and-serving/model-router.md)** — Once shadow evaluation produces a promotion decision, the model router executes the traffic shift.
- **[Span-Level Tracing](span-level-tracing.md)** — Trace both production and shadow requests end-to-end; compare not just response quality but latency breakdown by component.

## Further Reading

- [The Tail at Scale — Dean and Barroso, Google](https://research.google/pubs/pub40801/) — Origins of shadow traffic in distributed systems
- [Designing Machine Learning Systems — Chip Huyen](https://www.oreilly.com/library/view/designing-machine-learning/9781098107956/) — Chapter on evaluation and model deployment strategies
- [Continuous Delivery for Machine Learning (CD4ML)](https://martinfowler.com/articles/cd4ml.html) — Shadow testing as a deployment strategy for ML models
- [Braintrust: LLM Evaluation Platform](https://www.braintrust.dev/docs) — Practical tooling for production model comparison
