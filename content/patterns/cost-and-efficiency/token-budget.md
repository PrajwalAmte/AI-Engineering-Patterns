---
title: Token Budget
pillar: cost-and-efficiency
status: validated-in-production
tags: [cost, tokens, context-window, budgeting]
related:
  - Context Compaction
  - Cascading Context Assembly
  - Retrieval Quality Gate
  - LLM Gateway
example: examples/cost_and_efficiency/token_budget.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Give each part of the prompt its own token budget, always reserve room for the answer, and trim in a fixed, explainable order.
sidebar:
  order: 1
---

## What It Is

The context window is split into explicit budgets: system prompt, conversation history, retrieved context, user input, and a reserve for the model's output. When a component exceeds its budget, it's trimmed by a rule you chose in advance (least relevant chunks first, then oldest turns), not by whatever the SDK does when the request is too long.

There are two hard rules. Never silently cut the system prompt or the user's question. If either doesn't fit, reject with a clear error.

## The Problem It Solves

Without budgets, prompt size is decided by accident. Retrieval returns 20 chunks because `k=20` was the default. A long conversation pushes the window to 99% full, and the model's answer stops mid-sentence because no room was left for output. Someone adds three few-shot examples and every request gets 30% more expensive.

Then the provider's error, or worse, its silent truncation, decides what the model sees. Often that means losing the start of the prompt, which is where your instructions live.

## How It Works

<pre class="mermaid">
flowchart LR
    W["Context window"] --> R["Reserve output tokens"]
    R --> S["System prompt<br/>(over budget → error)"]
    R --> U["User input<br/>(over budget → ask user)"]
    R --> C["Retrieved chunks<br/>(keep most relevant that fit)"]
    R --> H["History<br/>(keep most recent that fit)"]
    S & U & C & H --> P["Prompt + per-component token log"]
</pre>

1. **Reserve output first.** Window minus reserve is your input budget. This alone prevents the most common truncation bug.
2. **Give each component a budget** that reflects what it's worth for this feature. A RAG answerer spends on retrieved chunks. A chat companion spends on history.
3. **Count with the model's tokenizer** (or the provider's token-counting endpoint). Word counts are fine in tests, not in production.
4. **Trim in a fixed order:** least relevant chunks, then oldest turns. For anything smarter than dropping old turns, use [Context Compaction](context-compaction.md).
5. **Log tokens per component** on every request. That's the data for tuning budgets and for answering "why did cost jump?"

## When to Use It

- Any prompt assembled from variable-length parts. That's almost every RAG and chat feature.
- You care about cost per request being predictable.
- You've seen truncated answers or "context length exceeded" errors in production.

## When NOT to Use It

- **Fixed prompts with short, bounded inputs** (classify this tweet). The budget is implicit and trivially met.
- **As a replacement for relevance filtering.** A budget decides how *much* context fits. A [Retrieval Quality Gate](../retrieval-and-memory/retrieval-quality-gate.md) decides whether it's worth including at all. Filling a budget with weak chunks is still a waste.

## Trade-offs

- **Fixed budgets waste space.** A short conversation leaves its history budget unused while retrieval is capped. Let unused budget flow to the next component in priority order if this matters to you.
- **Trimming loses information,** by design. The fixed order makes the loss predictable and explainable, which is the point.
- **Tokenizers differ between models.** A budget tuned for one model can be 10–20% off for another. Re-measure when you switch.

## Failure Modes

**No output reserve.** The input fills the window and the answer stops after 40 tokens. The usual symptom is "the model sometimes stops mid-sentence on long conversations". Reserve output explicitly.

**Truncating the wrong end.** A generic truncation helper cuts from the start of the prompt and removes the system instructions. Never truncate the assembled prompt. Trim individual components.

**Budgets that don't add up.** Component budgets sum to more than the window, so every component is within budget and the request still fails. Validate the configuration, as the example does.

## Implementation Example

Per-component budgets, an output reserve, relevance-ordered chunk selection, recency-ordered history, hard failures for the system prompt and user input, and a per-component token log.

```bash
cd examples && pytest cost_and_efficiency/test_token_budget.py
```

<!-- example: examples/cost_and_efficiency/token_budget.py -->
```python
"""Token Budget.

Split the context window into per-component budgets, reserve room for the
answer, and trim in a fixed order when something is over: least relevant
chunks first, then oldest conversation turns. Never silently cut the system
prompt or the user's question; if those alone don't fit, reject the request.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


class OverBudget(Exception):
    pass


@dataclass
class Budget:
    context_window: int = 32_000
    reserve_output: int = 2_000
    system: int = 2_000
    history: int = 6_000
    retrieved: int = 12_000
    user: int = 4_000


@dataclass
class Assembled:
    system: str
    history: list[str]
    chunks: list[str]
    user: str
    tokens: dict[str, int] = field(default_factory=dict)
    dropped: dict[str, int] = field(default_factory=dict)

    def prompt(self) -> str:
        return "\n\n".join([self.system, *self.history, *self.chunks, self.user])


def assemble(
    system: str,
    history: list[str],  # oldest first
    chunks: list[tuple[str, float]],  # (text, relevance)
    user: str,
    budget: Budget,
    count: Callable[[str], int],
) -> Assembled:
    total_in = budget.context_window - budget.reserve_output
    if count(system) > budget.system:
        raise OverBudget("system prompt exceeds its budget; fix the prompt, don't truncate it")
    if count(user) > budget.user:
        raise OverBudget("user input too long; ask the user to shorten it or attach it as a file")

    # Retrieved context: keep the most relevant chunks that fit.
    kept_chunks, used = [], 0
    for text, _ in sorted(chunks, key=lambda c: -c[1]):
        t = count(text)
        if used + t <= budget.retrieved:
            kept_chunks.append(text)
            used += t

    # History: keep the most recent turns that fit, in original order.
    kept_history, used_h = [], 0
    for turn in reversed(history):
        t = count(turn)
        if used_h + t > budget.history:
            break
        kept_history.insert(0, turn)
        used_h += t

    result = Assembled(system, kept_history, kept_chunks, user)
    result.tokens = {
        "system": count(system),
        "history": used_h,
        "retrieved": used,
        "user": count(user),
        "reserved_output": budget.reserve_output,
    }
    result.dropped = {"chunks": len(chunks) - len(kept_chunks), "turns": len(history) - len(kept_history)}
    if sum(v for k, v in result.tokens.items() if k != "reserved_output") > total_in:
        raise OverBudget("component budgets add up to more than the context window minus output reserve")
    return result
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| tiktoken, Hugging Face tokenizers | Exact counts for OpenAI and open models |
| Anthropic token counting API | Counts tokens for a full request, including tools and images |
| LangChain `trim_messages`, LlamaIndex memory buffers | Token-limited history helpers |

## Related Patterns

- [Context Compaction](context-compaction.md) is what to do with history when dropping old turns is too lossy.
- [Cascading Context Assembly](cascading-context-assembly.md) spends the retrieval budget gradually instead of all at once.
- [Retrieval Quality Gate](../retrieval-and-memory/retrieval-quality-gate.md) makes sure the budget goes on relevant chunks.
- [LLM Gateway](../inference-and-serving/llm-gateway.md) budgets across teams. This pattern budgets within one request.

## Further Reading

- [How to count tokens with tiktoken](https://cookbook.openai.com/examples/how_to_count_tokens_with_tiktoken), OpenAI Cookbook
- [Token counting](https://docs.anthropic.com/en/docs/build-with-claude/token-counting), Anthropic documentation
- [Lost in the Middle: How Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172), Liu et al., 2023. Why more context isn't free even when it fits.
