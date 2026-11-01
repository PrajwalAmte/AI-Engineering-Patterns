---
title: Cascading Context Assembly
pillar: cost-and-efficiency
status: emerging
tags: [cost, context-window, retrieval, latency]
related:
  - Token Budget
  - Model Router
  - Retrieval Quality Gate
  - Uncertainty-Triggered Retry
example: examples/cost_and_efficiency/cascading_context_assembly.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Answer with a little context first, and retrieve more only when the model says, with an exact sentinel, that it can't answer from what it has.
sidebar:
  order: 2
---

## What It Is

Instead of filling every prompt with the maximum retrieved context, start small. Give the model the top one or two chunks and an instruction: if the answer isn't in this context, reply with exactly `INSUFFICIENT_CONTEXT`. If it does, retrieve more (and optionally switch to a stronger model) and try again. Stop at the first tier that answers.

It's the [Model Router](../inference-and-serving/model-router.md) idea applied to context size instead of model size, and related to adaptive-retrieval research such as Adaptive-RAG and Self-RAG.

## The Problem It Solves

"Retrieve 20 chunks, just to be safe" is expensive in two ways. Every request pays for 20 chunks of input tokens, even "what are your opening hours?", which the first chunk answers. And more context isn't neutral: irrelevant chunks dilute attention, so answers to easy questions can get *worse* with more context.

But some questions really do need many chunks. A single fixed `k` is wrong for most traffic in one direction or the other.

## How It Works

<pre class="mermaid">
flowchart TD
    Q["Question"] --> T1["Tier 1: top 1–2 chunks, small model"]
    T1 -->|"answer"| R["Return"]
    T1 -->|"INSUFFICIENT_CONTEXT"| T2["Tier 2: top 5–8 chunks"]
    T2 -->|"answer"| R
    T2 -->|"INSUFFICIENT_CONTEXT"| T3["Tier 3: top 15–20 (+ rerank, stronger model)"]
    T3 -->|"answer"| R
    T3 -->|"INSUFFICIENT_CONTEXT"| M["Honest 'not found'"]
</pre>

1. **Define tiers** as (number of chunks, model) pairs. The last tier is your current "maximum" setup.
2. **Use an exact sentinel.** Asking the model to reply with a fixed token is far easier to detect, and more reliable, than parsing hedges or asking for a confidence number.
3. **Escalate on the sentinel only.** An answer at tier 1 is final.
4. **End with an honest miss.** If even the widest tier can't answer, say so. Don't let the model improvise.
5. **Log which tier answered.** If most traffic needs tier 3, your tier 1 is too thin, or retrieval ranking is off.

## When to Use It

- Retrieval-heavy features where most questions are answered by the top few chunks.
- Input tokens are a significant share of cost.
- An extra round-trip on the minority of hard questions is acceptable.

## When NOT to Use It

- **Latency-critical paths.** An escalated question pays for two or three sequential calls. If p99 latency matters more than cost, retrieve generously once.
- **Questions that are almost always broad** (summaries, comparisons). They'll escalate every time, so start at the wide tier.
- **Models that won't admit insufficiency.** Some models answer from training data rather than saying the sentinel. Test this. If false answers at tier 1 are common, add a [Grounding Verifier](../retrieval-and-memory/grounding-verifier.md) or skip this pattern.

## Trade-offs

- **Cost per question drops, and variance rises.** Easy questions get cheaper, hard ones more expensive (they pay for every failed tier).
- **Latency becomes bimodal.** Dashboards that show only the average will hide the slow tail of escalated questions.
- **It depends on the model being honest.** The pattern relies on the model saying "I can't answer from this" instead of guessing. Measure the guessing rate on questions where you know tier 1 doesn't have the answer.

## Failure Modes

**Confident answers from too little context.** Tier 1 doesn't contain the answer, and the model answers from general knowledge without using the sentinel. Use explicit "using only the context below" wording, evaluate it on held-out questions, and add a grounding check on tier-1 answers if this persists.

**Escalation storms.** A retrieval ranking regression pushes the right chunk from position 1 to 6, and suddenly every question escalates. Alert on the tier distribution, not just on cost.

**Re-retrieving what you already had.** Tier 2 re-fetches tier 1's chunks plus more, which is fine, but it shouldn't re-run expensive steps like query rewriting each time. Cache within the request.

## Implementation Example

Tiers as (k, model), an exact insufficiency sentinel, escalation only on that sentinel, and an honest miss at the end. The test reader can only answer when the right document is in its context, which makes escalation observable.

```bash
cd examples && pytest cost_and_efficiency/test_cascading_context_assembly.py
```

<!-- example: examples/cost_and_efficiency/cascading_context_assembly.py -->
```python
"""Cascading Context Assembly.

Answer with a little context first. Only if the model says it can't answer
from that, retrieve more and try again. Most questions stop at the first
tier; the few that need everything still get it.

The model is asked to reply with an exact sentinel when the context is
insufficient, which is far more reliable to detect than hedging language.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

INSUFFICIENT = "INSUFFICIENT_CONTEXT"

PROMPT = """Answer the question using only the context below.
If the context does not contain the answer, reply with exactly {sentinel} and nothing else.

Context:
{context}

Question: {question}"""


@dataclass
class Tier:
    k: int  # chunks to retrieve
    llm: Callable[[str], str]  # the last tier often uses a stronger model


@dataclass
class Result:
    answer: str
    tier: int  # 0-based index of the tier that answered
    chunks_used: int
    calls: int


def answer(
    question: str,
    retrieve: Callable[[str, int], list[str]],  # (query, k) -> chunks, best first
    tiers: list[Tier],
) -> Result:
    for i, tier in enumerate(tiers):
        chunks = retrieve(question, tier.k)
        reply = tier.llm(PROMPT.format(sentinel=INSUFFICIENT, context="\n---\n".join(chunks), question=question))
        if INSUFFICIENT not in reply:
            return Result(reply.strip(), i, len(chunks), i + 1)
    # Even the widest tier couldn't answer: say so rather than letting the model guess.
    return Result("I couldn't find that in the available documents.", len(tiers) - 1, len(chunks), len(tiers))
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| LlamaIndex, LangChain | Router and retriever components to build tiered retrieval |
| LangGraph | Conditional edges for "retrieve more" loops |
| Your gateway's model routing | Pair later tiers with stronger models |

## Related Patterns

- [Token Budget](token-budget.md) caps the widest tier.
- [Model Router](../inference-and-serving/model-router.md) uses the same escalation idea for model choice. The two combine naturally.
- [Retrieval Quality Gate](../retrieval-and-memory/retrieval-quality-gate.md) can make tier 1 more trustworthy by keeping only chunks that clearly answer the question.
- [Uncertainty-Triggered Retry](../reliability/uncertainty-triggered-retry.md) escalates on unsure answers. This pattern escalates on missing context.

## Further Reading

- [Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question Complexity](https://arxiv.org/abs/2403.14403), Jeong et al., 2024
- [Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection](https://arxiv.org/abs/2310.11511), Asai et al., 2023
- [FrugalGPT](https://arxiv.org/abs/2305.05176), Chen, Zaharia and Zou, 2023. LLM cascades.
