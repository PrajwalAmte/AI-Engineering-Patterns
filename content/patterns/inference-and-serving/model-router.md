---
title: Model Router
pillar: inference-and-serving
status: validated-in-production
tags: [routing, cost, latency, model-selection]
related:
  - LLM Gateway
  - Semantic Caching
  - Effort Scaling
  - LLM-as-Judge
example: examples/inference_and_serving/model_router.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Send each query to the cheapest model that can handle it, and escalate when the cheap answer doesn't pass a check.
sidebar:
  order: 2
---

## What It Is

A router looks at a query before any model sees it and picks a tier: a small, fast model for easy queries and a large one for hard queries. If the cheap model's answer fails a check, the router escalates to the next tier.

The decision can be a few rules, a small trained classifier, or a call to a cheap model. Most teams start with rules, collect data, and train a classifier later.

## The Problem It Solves

Look at a day of real traffic for almost any assistant and you'll find that most queries are easy: lookups, reformatting, short factual answers. A smaller model handles these as well as the flagship does. Teams still send everything to the flagship, because it was the model used in the demo and nobody wants to be the one who made answers worse.

The result is that you pay flagship prices for "what's your refund policy?" The size of the waste depends on your traffic mix, so measure it. Replay a sample of logged queries through a smaller model and compare the answers before you build anything.

## How It Works

<pre class="mermaid">
flowchart TD
    Q["Query"] --> S["Score complexity"]
    S -->|"low"| T1["Small model"]
    S -->|"high"| T2["Large model"]
    T1 --> C{"Answer passes check?"}
    C -->|"yes"| R["Return"]
    C -->|"no: escalate"| T2
    T2 --> R
    C -.->|"escalation rate per tier"| M["Monitor and retune thresholds"]
</pre>

1. **Score the query.** Start with signals you can compute for free: length, reasoning words ("why", "compare", "design"), code, and conversation depth.
2. **Pick the cheapest tier** whose threshold covers the score.
3. **Check the answer.** The check can be as simple as "not empty and not a refusal", or a schema validation, or a cheap judge call for high-stakes paths.
4. **Escalate on rejection,** one tier at a time.
5. **Watch the escalation rate per tier.** If it climbs, the router is sending queries that are too hard to the small model. You'll see this before average quality moves.

## When to Use It

- Your traffic is a mix of easy and hard queries, and you pay one model's price for all of them.
- You can check answers automatically, at least roughly. Without a check you can't escalate and you can't tell whether the router is working.
- Inference spend is big enough that halving it matters to someone.

## When NOT to Use It

- **Every query is hard.** A code-generation agent where every request is a multi-file change gains nothing from routing.
- **You can't measure quality.** Routing blind means saving money while quality drifts without anyone noticing.
- **Spend is small.** If inference costs a few hundred dollars a month, a router costs more in engineering time than it saves.

## Trade-offs

- **Misroutes go both ways.** A hard query sent to a small model gives a bad answer (escalation catches some of these). An easy query sent to a large model wastes money, and nobody complains about that, so you have to measure it.
- **Escalation adds latency.** An escalated query pays for two model calls. If more than about 20% of a tier's traffic escalates, that tier's threshold is set too generously.
- **Model releases move the boundaries.** Each new small model raises what "easy" means, so plan to retune thresholds after every model upgrade.

## Failure Modes

**Confidently wrong cheap answers.** The small model gives a fluent, well-formed, wrong answer. The check passes and nobody escalates. Format checks can't catch this. Sample a few percent of small-tier answers, grade them with a stronger model ([LLM-as-Judge](../observability-and-evaluation/llm-as-judge.md)), and track the disagreement rate.

**Traffic drift.** A new feature launches and its queries look short and simple but need domain knowledge. The rules were written for last quarter's traffic, so these queries go to the small model. Break down quality and escalation rate by tier *and* by feature, not just overall.

**Collapse under rate limits.** The small tier hits its provider rate limit, and the fallback logic sends everything to the large tier. Costs jump while the dashboards look green. Alert when a tier's share of traffic moves outside its normal range.

## Implementation Example

A rule-based router with escalation and per-tier counters. It's a deliberately simple starting point: it's easy to inspect, and the counters give you the labelled data to train something better later.

```bash
cd examples && pytest inference_and_serving/test_model_router.py
```

<!-- example: examples/inference_and_serving/model_router.py -->
```python
"""Model Router.

Send each query to the cheapest model tier that can handle it, and escalate
when the cheap answer fails a check. Start with rules like these; replace the
scoring function with a trained classifier once you have labelled traffic.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

REASONING_HINTS = re.compile(
    r"\b(why|explain|compare|trade-?offs?|prove|design|debug|step by step|analy[sz]e|plan)\b", re.I
)
CODE_HINTS = re.compile(r"```|def |class |SELECT |stack trace|Traceback", re.I)


@dataclass
class Tier:
    name: str
    model: Callable[[str], str]
    max_score: float  # this tier takes queries scoring up to this value


def complexity_score(query: str, turns: int = 1) -> float:
    """0.0 = trivial lookup, 1.0 = hard multi-step reasoning. Crude on purpose."""
    score = min(len(query.split()) / 200, 0.4)
    score += 0.25 * min(len(REASONING_HINTS.findall(query)), 2)
    score += 0.2 if CODE_HINTS.search(query) else 0.0
    score += 0.1 if turns > 6 else 0.0
    return min(score, 1.0)


@dataclass
class ModelRouter:
    tiers: list[Tier]  # cheapest first
    accept: Callable[[str, str], bool] = lambda query, answer: bool(answer.strip())
    stats: Counter = field(default_factory=Counter)

    def pick(self, query: str, turns: int = 1) -> int:
        score = complexity_score(query, turns)
        for i, tier in enumerate(self.tiers):
            if score <= tier.max_score:
                return i
        return len(self.tiers) - 1

    def answer(self, query: str, turns: int = 1) -> tuple[str, str]:
        """Returns (answer, tier_name). Escalates one tier at a time on rejection."""
        start = self.pick(query, turns)
        self.stats[f"routed:{self.tiers[start].name}"] += 1
        answer = ""
        for tier in self.tiers[start:]:
            answer = tier.model(query)
            if self.accept(query, answer):
                return answer, tier.name
            # Track escalations per tier: a rising rate means the router or the
            # cheap model has drifted, long before average quality moves.
            self.stats[f"escalated_from:{tier.name}"] += 1
        return answer, self.tiers[-1].name
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| RouteLLM | Open-source framework and trained routers from LMSYS; good for learning how learned routing works |
| Not Diamond, Martian | Managed routers that pick a model per prompt |
| LiteLLM, Portkey | Rule-based and conditional routing at the gateway |
| OpenRouter | Single API across many models, with fallbacks; you write the routing logic |

## Related Patterns

- [LLM Gateway](llm-gateway.md) carries out the routing decision. Router logic usually lives inside it.
- [Semantic Caching](semantic-caching.md) runs first: a cache hit skips routing entirely.
- [Effort Scaling](../cost-and-efficiency/effort-scaling.md) is the same idea applied to reasoning budget instead of model choice.
- [LLM-as-Judge](../observability-and-evaluation/llm-as-judge.md) audits whether cheap-tier answers are actually good enough.

## Further Reading

- [RouteLLM: Learning to Route LLMs with Preference Data](https://arxiv.org/abs/2406.18665), Ong et al., 2024
- [FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance](https://arxiv.org/abs/2305.05176), Chen, Zaharia and Zou, 2023. The original LLM cascade paper.
