---
title: Model Router
pillar: inference-and-serving
status: validated-in-production
tags: [routing, cost, latency, model-selection]
related:
  - LLM Gateway Pattern
  - Semantic Caching
  - Tiered Model Strategy
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Route queries to cheap/fast models vs powerful ones based on complexity for 85-99% cost reduction.
sidebar:
  order: 2
---

## What It Is

A model router classifies incoming queries by complexity and routes them to the appropriate model tier. Simple queries go to fast, cheap models. Complex queries go to powerful, expensive models. The router itself can be a lightweight classifier, an LLM judge, or a rule-based system.

## The Problem It Solves

Most production workloads have a highly skewed complexity distribution. Typically 70-90% of queries are simple enough for a small, fast model, but teams route everything to a single powerful (expensive) model because they lack a mechanism to differentiate. This results in 5-20x higher costs than necessary.

## How It Works

```
Query → Router (classify complexity)
            │
    ┌───────┼───────┐
    │       │       │
  Simple  Medium  Complex
    │       │       │
  GPT-4o   Claude  Claude
  mini    Sonnet   Opus
    │       │       │
    └───────┴───────┘
            │
        Response
```

1. A query arrives at the router.
2. The router classifies the query into a complexity tier using one of:
   - **Rule-based**: Query length, keyword presence, conversation turn count.
   - **Classifier**: A lightweight ML model trained on labeled query-complexity pairs.
   - **LLM judge**: A cheap model scores the query complexity before routing (adds latency but is more accurate).
3. Based on the tier, the query is sent to the corresponding model.
4. Quality monitoring compares outputs across tiers to validate routing accuracy.
5. Misrouted queries (simple queries that needed the powerful model) are logged and used to retrain the router.

## When to Use It

- Your workload has a mix of simple and complex queries and you are paying a single-model price for all of them.
- You have measurable quality criteria that let you verify whether a cheaper model's output is acceptable.
- Cost reduction of 50%+ would meaningfully change the economics of your product.
- You can tolerate occasional quality misses on misrouted queries (with fallback to a better model).

## When NOT to Use It

- All your queries are roughly the same complexity (e.g., a specialized code generation tool where every query is complex). The router adds latency with no cost savings.
- You cannot measure output quality automatically. Without quality feedback, you cannot validate that cheaper models are performing adequately.
- Your query volume is low enough that the cost difference is negligible. If you spend less than a few hundred dollars per month on inference, the engineering effort of maintaining a router is not justified.
- Latency is more critical than cost, and the routing decision itself adds unacceptable overhead.

## Trade-offs

1. **Routing accuracy vs. cost** — Misrouting a complex query to a cheap model produces bad output. Misrouting a simple query to an expensive model wastes money. Finding the balance requires ongoing calibration.
2. **Added latency** — Any classification step adds latency before the actual inference. Rule-based routers add microseconds; LLM-judge routers add hundreds of milliseconds.
3. **Maintenance burden** — As models evolve and new tiers appear, the router needs updating. Model capabilities change with each release.
4. **Quality monitoring dependency** — The router is only as good as your ability to detect when it routes incorrectly. Requires investment in evaluation and feedback loops.

## Implementation Example

```python
from dataclasses import dataclass
from enum import Enum


class Tier(Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass
class RouteResult:
    tier: Tier
    model: str
    reason: str


TIER_MODELS = {
    Tier.SIMPLE: "gpt-4o-mini",
    Tier.MEDIUM: "claude-3-5-sonnet-20241022",
    Tier.COMPLEX: "claude-3-5-opus-20260301",
}

COMPLEXITY_KEYWORDS = {
    "analyze", "compare", "synthesize", "evaluate",
    "multi-step", "trade-off", "architecture", "design",
}


def classify_query(query: str, has_context: bool = False) -> RouteResult:
    words = query.lower().split()
    word_count = len(words)
    has_complexity_keywords = bool(set(words) & COMPLEXITY_KEYWORDS)

    if word_count < 20 and not has_complexity_keywords and not has_context:
        tier = Tier.SIMPLE
        reason = "Short query without complexity indicators"
    elif word_count > 100 or (has_complexity_keywords and has_context):
        tier = Tier.COMPLEX
        reason = "Long query with complexity indicators and context"
    else:
        tier = Tier.MEDIUM
        reason = "Moderate complexity"

    return RouteResult(
        tier=tier,
        model=TIER_MODELS[tier],
        reason=reason,
    )


async def routed_completion(gateway, query: str, messages: list[dict]) -> dict:
    route = classify_query(query)
    return await gateway.chat_completion(
        model=route.model,
        messages=messages,
    )
```

For production systems, replace the rule-based classifier with a trained lightweight model (e.g., a fine-tuned BERT classifier or a logistic regression over query features) and add quality-based feedback to continuously improve routing decisions.

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| Martian | Managed router | ML-based model router with automatic quality monitoring |
| Unify AI | Managed router | Routes across 100+ models based on quality/cost/latency targets |
| RouteLLM (Berkeley) | Open-source | Research framework for training LLM routers |
| Portkey | Gateway with routing | Conditional routing rules at the gateway level |
| Custom classifier | DIY | Maximum control, requires labeled data and evaluation infrastructure |

## Related Patterns

- **[LLM Gateway Pattern](/patterns/inference-and-serving/llm-gateway/)** — The gateway executes the routing decision. Router logic often lives inside the gateway.
- **[Semantic Caching](/patterns/inference-and-serving/semantic-caching/)** — Check the cache before routing. Cached responses bypass model selection entirely.
- **[Tiered Model Strategy](/patterns/cost-and-efficiency/tiered-model-strategy/)** — The broader cost strategy that model routing implements.
- **[Cost Attribution Pattern](/patterns/observability/cost-attribution/)** — Measures cost savings from routing to validate the approach.
- **[Quality Drift Detection](/patterns/observability/quality-drift-detection/)** — Detects when routing decisions degrade output quality over time.

## Further Reading

- [RouteLLM: Learning to Route LLMs with Preference Data (Berkeley, 2024)](https://arxiv.org/abs/2406.18665)
- [Martian Model Router — How It Works](https://withmartian.com/blog/model-router)
- [Not All Tokens Are Equal: Cost-Efficient LLM Serving](https://arxiv.org/abs/2404.08865)
