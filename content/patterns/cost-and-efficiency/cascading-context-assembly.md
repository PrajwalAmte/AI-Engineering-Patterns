---
title: Cascading Context Assembly
pillar: cost-and-efficiency
status: emerging
tags: [cost, context-window, retrieval, latency, efficiency]
related:
  - Token Budget Pattern
  - Model Router Pattern
  - Hybrid Search
  - Semantic Caching
contributors: ["@PrajwalAmte"]
last_updated: "2026-04"
description: Start with minimal context and progressively enrich only when the model signals low confidence, avoiding maximum context stuffing on every request.
sidebar:
  order: 2
---

## What It Is

Cascading context assembly is a multi-tier retrieval and prompting strategy that starts with the cheapest, smallest context and only escalates to richer context when the model's initial response signals low confidence or insufficient information. Instead of stuffing every request with maximum context, it builds context progressively — spending retrieval cost and context window tokens only when needed.

## The Problem It Solves

The default RAG architecture retrieves a fixed number of chunks for every query and stuffs them all into the prompt. This "max context by default" approach has compounding costs:

- **Token waste on easy queries**: "What is your refund policy?" could be answered from a single short chunk. Instead, the system retrieves 10 chunks, pays for 4,000 input tokens, and the LLM ignores 9 of them. Across thousands of requests, this waste is substantial.
- **Latency floor**: More context means more input tokens, which means higher time-to-first-token. Even when the answer is trivially available, the system pays the latency cost of processing unnecessary context.
- **Retrieval noise**: Retrieving more chunks increases the chance of including irrelevant or contradictory information. The LLM must filter signal from noise in the context, which can degrade answer quality — more is not always better.
- **Fixed cost regardless of difficulty**: A one-line factual lookup and a complex multi-document synthesis task consume the same retrieval and context budget. There is no cost differentiation by query complexity.

Cascading context assembly aligns cost with difficulty: simple queries get simple (cheap) context, and only complex queries pay for rich context.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Query arrives"] --> B["Tier 1: minimal context (1-2 chunks)"]
    B --> C["LLM generates response + confidence signal"]
    C --> D{"Confidence above threshold?"}
    D -->|"Yes"| E["Return response"]
    D -->|"No"| F["Tier 2: expanded context (5-8 chunks)"]
    F --> G["LLM generates response + confidence signal"]
    G --> H{"Confidence above threshold?"}
    H -->|"Yes"| I["Return response"]
    H -->|"No"| J["Tier 3: full context (max chunks + reranking)"]
    J --> K["LLM generates final response"]
    K --> L["Return response"]
</pre>

1. **Tier 1 — Minimal context**: Retrieve the top 1-2 most relevant chunks. Send to the LLM with an instruction to answer if confident, or respond with a structured "insufficient context" signal if not.
2. **Confidence evaluation**: Parse the LLM's response for a confidence signal. This can be an explicit confidence score (asked for in the prompt), a refusal phrase ("I don't have enough information"), or log-probability analysis on the response tokens.
3. **Tier 2 — Expanded context**: If Tier 1 signals low confidence, retrieve additional chunks (5-8 total) using broader search or a different retrieval strategy (switching from pure vector to hybrid search). Re-prompt with the richer context.
4. **Tier 3 — Full context**: If Tier 2 still signals low confidence, pull maximum context with reranking, multi-source retrieval, and optionally a stronger model. This is the "spare no expense" tier reserved for genuinely difficult queries.
5. **Response**: Return the response from the first tier that achieves sufficient confidence. Most queries resolve at Tier 1 or Tier 2.

## When to Use It

- Your query distribution has a long tail: most queries are simple, but some require deep retrieval. You are paying Tier 3 costs for Tier 1 queries.
- Cost reduction is a priority and you have sufficient request volume for the savings to be meaningful.
- Latency matters and you want to serve simple queries faster without a blanket latency increase from large contexts.
- Your retrieval quality degrades with more chunks (retrieval noise is a measured problem, not a theoretical concern).

## When not to Use It

- Most queries genuinely require deep context (legal analysis, research synthesis). If Tier 3 fires on 80%+ of queries, cascading adds latency (multiple LLM calls) without saving cost.
- The LLM cannot reliably signal low confidence. If the model confidently hallucinates at Tier 1 instead of admitting insufficient context, cascading produces wrong answers faster. Test confidence calibration before adopting this pattern.
- Your retrieval is already cheap (small index, local embedding model, low per-token costs). The cost of an extra LLM call to evaluate confidence may exceed the savings from reduced context.
- Strict latency SLOs that cannot tolerate the occasional multi-tier cascade. Worst-case latency increases because hard queries now take 2-3 serial LLM calls.

## Trade-offs

1. **Confidence calibration** — The entire pattern depends on the LLM's ability to say "I don't know" when context is insufficient. Many models default to generating plausible-sounding answers. Prompt engineering and model selection are critical to making this work.
2. **Latency variance** — Easy queries are faster, but hard queries are slower (multiple serial LLM calls). P50 improves, P99 may worsen. This variance may be unacceptable for some use cases.
3. **Prompt complexity** — Each tier needs a prompt that elicits a usable confidence signal without being so cautious that the model refuses to answer on sufficient context.
4. **Cascading errors** — If Tier 1 confidently returns a wrong answer, the cascade stops early with a bad response. The system optimizes for cost at the risk of missing cases where more context would have corrected the answer.

## Failure Modes

### Over-Confident Early Exit
**Trigger**: The model reports high confidence at Tier 1 because it has strong priors from training data, even though the domain-specific answer differs from its parametric knowledge.
**Symptom**: The system serves wrong answers cheaply and confidently. Quality metrics look fine in aggregate because most queries are correctly answered at Tier 1, but a class of domain-specific queries consistently fails.
**Mitigation**: Validate confidence calibration on a held-out set of queries where the answer requires domain context (not general knowledge). Force a random sample of Tier 1 exits through the full cascade to measure the miss rate.

### Tier Configuration Drift
**Trigger**: New context sources are added to the system but not wired into the cascade tiers, or tier costs change (embedding model updated, new retrieval index).
**Symptom**: The cascade skips a relevant context source. Cost assumptions are wrong — a "cheap" tier is now expensive, and the cascade does not save money anymore.
**Mitigation**: Document the cascade tier configuration as code. Review tier composition and cost assumptions on a schedule (monthly). Alert when per-tier cost-per-query deviates from expected range.

### Serial Latency Stacking
**Trigger**: A hard query fails confidence checks at every tier, causing sequential LLM calls at Tier 1, Tier 2, and Tier 3.
**Symptom**: Worst-case latency is the sum of all tier latencies. P99 latency spikes to 3x the single-call latency. Users on hard queries experience unacceptable wait times.
**Mitigation**: Set a total cascade timeout. If the budget is exhausted, return the best response so far with a confidence disclaimer rather than continuing to cascade.

## Implementation Example

```python
from dataclasses import dataclass
from enum import Enum


class ConfidenceLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


@dataclass
class TierResult:
    response: str
    confidence: ConfidenceLevel
    tier: int
    chunks_used: int
    input_tokens: int


TIER_PROMPT_SUFFIX = (
    "\n\nAfter your answer, on a new line, provide your confidence level "
    "as exactly one of: [HIGH_CONFIDENCE], [MEDIUM_CONFIDENCE], [LOW_CONFIDENCE], "
    "[INSUFFICIENT_CONTEXT]. Use [INSUFFICIENT_CONTEXT] if the provided context "
    "does not contain enough information to answer reliably."
)


def parse_confidence(response: str) -> tuple[str, ConfidenceLevel]:
    confidence_map = {
        "[HIGH_CONFIDENCE]": ConfidenceLevel.HIGH,
        "[MEDIUM_CONFIDENCE]": ConfidenceLevel.MEDIUM,
        "[LOW_CONFIDENCE]": ConfidenceLevel.LOW,
        "[INSUFFICIENT_CONTEXT]": ConfidenceLevel.INSUFFICIENT,
    }
    for tag, level in confidence_map.items():
        if tag in response:
            clean_response = response.replace(tag, "").strip()
            return clean_response, level
    return response, ConfidenceLevel.MEDIUM


class CascadingContextAssembler:
    def __init__(
        self,
        retrieve_fn,
        llm_fn,
        tier_configs: list[dict] | None = None,
        confidence_threshold: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    ):
        self._retrieve = retrieve_fn
        self._llm = llm_fn
        self._threshold = confidence_threshold
        self._tier_configs = tier_configs or [
            {"top_k": 2, "strategy": "vector"},
            {"top_k": 6, "strategy": "hybrid"},
            {"top_k": 12, "strategy": "hybrid_reranked"},
        ]

    def _is_sufficient(self, confidence: ConfidenceLevel) -> bool:
        rank = {
            ConfidenceLevel.HIGH: 3,
            ConfidenceLevel.MEDIUM: 2,
            ConfidenceLevel.LOW: 1,
            ConfidenceLevel.INSUFFICIENT: 0,
        }
        return rank[confidence] >= rank[self._threshold]

    def answer(self, query: str) -> TierResult:
        for tier_idx, config in enumerate(self._tier_configs):
            chunks = self._retrieve(
                query,
                top_k=config["top_k"],
                strategy=config["strategy"],
            )

            context = "\n\n---\n\n".join(chunks)
            prompt = (
                f"Answer the question using only the provided context.\n\n"
                f"Context:\n{context}\n\n"
                f"Question: {query}"
                f"{TIER_PROMPT_SUFFIX}"
            )

            raw_response = self._llm(prompt)
            clean_response, confidence = parse_confidence(raw_response)

            if self._is_sufficient(confidence) or tier_idx == len(self._tier_configs) - 1:
                return TierResult(
                    response=clean_response,
                    confidence=confidence,
                    tier=tier_idx + 1,
                    chunks_used=len(chunks),
                    input_tokens=len(prompt.split()) * 2,
                )

        return TierResult(
            response=clean_response,
            confidence=confidence,
            tier=len(self._tier_configs),
            chunks_used=len(chunks),
            input_tokens=len(prompt.split()) * 2,
        )
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| LlamaIndex Response Synthesizers | Framework | Supports compact, refine, and tree-summarize modes as escalation tiers |
| LangChain LCEL | Framework | Compose multi-step chains with conditional branching based on output |
| Semantic Kernel (Microsoft) | Framework | Planner can dynamically decide how much context to retrieve |
| Cohere Rerank | API | Useful as the escalation step between Tier 2 and Tier 3 |
| Custom pipeline | DIY | Necessary for tight control over tier boundaries and confidence parsing |

## Related Patterns

- **[Token Budget Pattern](/AI-Engineering-Patterns/patterns/cost-and-efficiency/token-budget/)** — Token budgets set the hard ceiling; cascading context decides how much of that budget to use per request.
- **[Model Router Pattern](/AI-Engineering-Patterns/patterns/inference-and-serving/model-router/)** — Can be combined: Tier 1 uses a cheap model with minimal context; Tier 3 uses a powerful model with full context.
- **[Hybrid Search](/AI-Engineering-Patterns/patterns/retrieval-and-memory/hybrid-search/)** — Tier escalation can switch retrieval strategies (vector-only at Tier 1, hybrid at Tier 2).
- **[Semantic Caching](/AI-Engineering-Patterns/patterns/inference-and-serving/semantic-caching/)** — Cache responses from all tiers. A Tier 1 cache hit avoids even the minimal retrieval cost.

## Further Reading

- [Adaptive Retrieval-Augmented Generation — Microsoft Research](https://arxiv.org/abs/2403.14403)
- [Self-RAG: Learning to Retrieve, Generate, and Critique (Asai et al., 2023)](https://arxiv.org/abs/2310.11511)
- [When Less is More: Investigating the Role of Context Length in RAG](https://arxiv.org/abs/2404.07981)
