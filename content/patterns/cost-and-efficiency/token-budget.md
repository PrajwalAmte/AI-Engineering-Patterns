---
title: Token Budget Pattern
pillar: cost-and-efficiency
status: validated-in-production
tags: [cost, tokens, budgeting, efficiency]
related:
  - Prompt Compression Pattern
  - Cost Circuit Breaker
  - Tiered Model Strategy
  - Cost Attribution Pattern
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Hard limits on input/output tokens per request with trimming or summarization when limits are hit.
sidebar:
  order: 1
---

## What It Is

The token budget pattern enforces hard limits on the number of input and output tokens per LLM request. When a request would exceed its budget, the system automatically trims, summarizes, or truncates the input to fit — rather than sending an oversized request that fails or costs more than expected.

## The Problem It Solves

Without token budgets, costs grow unpredictably. A single RAG query that retrieves too many chunks, a conversation with long history, or a verbose system prompt can easily create requests with 50,000+ input tokens — costing 10-50x what the same request should cost with proper budgeting.

Common runaway scenarios:

- A retrieval pipeline returns 20 chunks when 5 would suffice, inflating input tokens.
- Conversation history grows unbounded across turns, each turn adding the full history.
- A system prompt combined with a user query and retrieved context exceeds the model's context window, causing a hard failure.
- No per-request guardrail means one pathological request can consume a significant portion of the daily budget.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Request assembly"] --> B["Count tokens by component"]
    B --> C{"Within token budget?"}
    C -->|"Yes"| D["Reserve output tokens"]
    D --> E["Send prompt to model"]
    C -->|"No"| F["Trim variable context"]
    F --> F1["Drop lowest-relevance chunks"]
    F --> F2["Summarize older conversation turns"]
    F --> F3["Truncate as last resort"]
    F1 --> G["Recalculate token counts"]
    F2 --> G
    F3 --> G
    G --> C
    G --> H{"Still above hard limit?"}
    H -->|"Yes"| I["Reject request with clear budget error"]
    H -->|"No"| D
</pre>

1. **Define per-component budgets**: Allocate the total context window across fixed components (system prompt, few-shot examples) and variable components (retrieved context, conversation history, user input).
2. **Measure token counts**: Count tokens for each component before assembling the prompt. Use the model's tokenizer for accurate counts.
3. **Apply trimming strategies**: When a component exceeds its budget:
   - **Retrieved context**: Drop the lowest-relevance chunks until the budget is met.
   - **Conversation history**: Summarize older turns or drop them from oldest to newest.
   - **User input**: Truncate only as a last resort (rare — user inputs are usually short).
4. **Reserve output tokens**: Always reserve a portion of the context window for the model's output. A common mistake is filling the entire window with input, leaving no room for a meaningful response.
5. **Enforce hard limits**: If trimming cannot bring the request within budget, reject the request with a clear error rather than sending a degraded prompt.

## When to Use It

- You process requests with variable-length context (RAG, conversations, document analysis).
- Cost predictability is important for your business model (per-request pricing, free tier limits).
- You have experienced cost spikes from pathological inputs or runaway context accumulation.
- You need to prevent hard failures from exceeding model context windows.

## When not to Use It

- All your requests are short, fixed-format prompts with predictable token counts. Budgeting adds complexity to a system that does not need it.
- You are doing long-context tasks where the value comes from processing the full input (document summarization of a specific document, code analysis of an entire codebase). Trimming destroys the value of the task.
- Cost is not a concern and latency optimization (fewer tokens = faster) is not needed. Some research or internal workloads have effectively unlimited budgets.

## Trade-offs

1. **Information loss** — Trimming context removes potentially relevant information. The system may produce worse answers because it was forced to drop useful context.
2. **Implementation complexity** — Accurate token counting requires the model's specific tokenizer. Different models tokenize differently, so budgets are model-specific.
3. **User experience** — In conversation scenarios, summarizing or dropping history changes what the model "remembers." Users may experience inconsistent context awareness.
4. **Over-budgeting** — Setting budgets too conservatively wastes context window capacity. Setting them too loosely defeats the purpose.

## Failure Modes

### Tokenizer Mismatch
**Trigger**: Budget enforcement uses a different tokenizer than the target model (e.g., counting with `tiktoken` cl100k_base but sending to a model that uses a different tokenizer).
**Symptom**: Requests are either trimmed too aggressively (losing useful context) or not trimmed enough (exceeding the model's actual limit and causing API errors).
**Mitigation**: Use the exact tokenizer for the target model. When routing across models, re-count tokens per model. Abstract token counting behind the model router.

### Context Trimming Removes Critical Information
**Trigger**: Budget enforcement truncates retrieved context by position (e.g., drop the last chunks), and the most relevant information happens to be at the end.
**Symptom**: Model quality drops on queries where the answer was in the trimmed portion. The system appears to work but gives wrong answers on a subset of queries.
**Mitigation**: Trim by relevance score, not position. Sort context by retrieval score and trim the lowest-scored chunks first. Log what was trimmed for debugging.

### Budget Exhausted by System Prompt
**Trigger**: System prompt, few-shot examples, and tool definitions consume most of the token budget before user context is added.
**Symptom**: Almost no retrieved context fits within budget. Responses are generic or hallucinated because the model has instructions but no grounding data.
**Mitigation**: Account for system prompt tokens as a fixed overhead before allocating the retrieval budget. Alert when system prompt exceeds a predefined percentage of the total context window.

## Implementation Example

```python
from dataclasses import dataclass


@dataclass
class TokenBudget:
    system_prompt: int
    context: int
    conversation_history: int
    user_query: int
    output_reserve: int

    @property
    def total_input(self) -> int:
        return (
            self.system_prompt
            + self.context
            + self.conversation_history
            + self.user_query
        )

    @property
    def total(self) -> int:
        return self.total_input + self.output_reserve


def count_tokens(text: str) -> int:
    return len(text.split()) * 4 // 3


def trim_context_to_budget(
    chunks: list[dict],
    budget: int,
) -> list[dict]:
    trimmed = []
    used = 0
    for chunk in chunks:
        chunk_tokens = count_tokens(chunk["content"])
        if used + chunk_tokens > budget:
            break
        trimmed.append(chunk)
        used += chunk_tokens
    return trimmed


def trim_conversation_history(
    messages: list[dict],
    budget: int,
) -> list[dict]:
    total = sum(count_tokens(m["content"]) for m in messages)

    if total <= budget:
        return messages

    trimmed = list(messages)
    while trimmed and total > budget:
        removed = trimmed.pop(0)
        total -= count_tokens(removed["content"])

    return trimmed


def assemble_prompt(
    system_prompt: str,
    context_chunks: list[dict],
    conversation: list[dict],
    user_query: str,
    budget: TokenBudget,
) -> dict:
    system_tokens = count_tokens(system_prompt)
    if system_tokens > budget.system_prompt:
        raise ValueError(
            f"System prompt ({system_tokens} tokens) exceeds budget ({budget.system_prompt})"
        )

    query_tokens = count_tokens(user_query)
    if query_tokens > budget.user_query:
        raise ValueError(
            f"User query ({query_tokens} tokens) exceeds budget ({budget.user_query})"
        )

    trimmed_context = trim_context_to_budget(context_chunks, budget.context)
    trimmed_history = trim_conversation_history(conversation, budget.conversation_history)

    context_text = "\n\n".join(c["content"] for c in trimmed_context)

    messages = [
        {"role": "system", "content": system_prompt},
    ]

    if context_text:
        messages.append(
            {"role": "system", "content": f"Relevant context:\n{context_text}"}
        )

    messages.extend(trimmed_history)
    messages.append({"role": "user", "content": user_query})

    return {
        "messages": messages,
        "max_tokens": budget.output_reserve,
        "metadata": {
            "context_chunks_used": len(trimmed_context),
            "context_chunks_available": len(context_chunks),
            "history_messages_used": len(trimmed_history),
            "history_messages_available": len(conversation),
        },
    }


STANDARD_BUDGET = TokenBudget(
    system_prompt=500,
    context=3000,
    conversation_history=1000,
    user_query=500,
    output_reserve=1000,
)
```

For production systems, replace the approximation in `count_tokens` with the model's actual tokenizer (tiktoken for OpenAI models, the relevant HuggingFace tokenizer for others).

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| tiktoken | Open-source (OpenAI) | Fast BPE tokenizer for accurate token counting with OpenAI models |
| LangChain token counters | Framework utility | Built-in token counting and context trimming for chains |
| LiteLLM | Open-source proxy | Token counting and budget enforcement at the gateway level |
| Semantic Kernel | Framework (Microsoft) | Token management as part of the prompt orchestration layer |

## Related Patterns

- **[Prompt Compression Pattern](/AI-Engineering-Patterns/patterns/cost-and-efficiency/prompt-compression/)** — Reduce token count of context before it enters the budget. Compression happens before; budgeting enforces the limit.
- **[Cost Circuit Breaker](/AI-Engineering-Patterns/patterns/cost-and-efficiency/cost-circuit-breaker/)** — Aggregate budget enforcement at the system level, not per-request.
- **[Tiered Model Strategy](/AI-Engineering-Patterns/patterns/cost-and-efficiency/tiered-model-strategy/)** — Route to cheaper models to stretch the per-request cost budget.
- **[Cost Attribution Pattern](/AI-Engineering-Patterns/patterns/observability/cost-attribution/)** — Track actual token usage against budgets to identify over/under-allocation.
- **[Chunking Strategy Pattern](/AI-Engineering-Patterns/patterns/retrieval-and-memory/chunking-strategy/)** — Chunk size directly affects how many chunks fit in the context budget.

## Further Reading

- [Managing Token Limits in LLM Applications — OpenAI Cookbook](https://cookbook.openai.com/examples/how_to_count_tokens_with_tiktoken)
- [Context Window Management — Anthropic Documentation](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- [Lost in the Middle: How Language Models Use Long Contexts (Liu et al., 2023)](https://arxiv.org/abs/2307.03172)
