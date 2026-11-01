---
title: Span-Level Tracing
pillar: observability-and-evaluation
status: validated-in-production
tags: [observability, tracing, latency, cost, debugging]
related:
  - LLM Gateway
  - LLM-as-Judge
  - Multi-Agent Orchestration
  - Guardrails
example: examples/observability_and_evaluation/span_level_tracing.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: One trace per request, one span per pipeline step, with tokens and cost on every model call, so "why was this slow, expensive or wrong?" has an answer.
sidebar:
  order: 1
---

## What It Is

Distributed tracing, as you'd use for microservices, applied to the steps inside an AI request: embed, search, rerank, build the prompt, call the model, run guardrails, call tools. Each step is a span with a start, an end, a parent, and attributes. On model spans, the attributes include the model name, input and output tokens, and cost.

None of this is new. What's specific to AI is *what* you record. A plain APM trace shows "POST /chat took 4.2s". You need to know that 0.3s of that was the reranker, 3.6s was the model, and the prompt was 1,800 tokens because retrieval returned twenty chunks instead of five.

## The Problem It Solves

A user reports a slow, wrong answer. Without spans, you know the request took 9 seconds and returned something bad. You don't know whether retrieval found the wrong documents, the reranker dropped the right one, the prompt was truncated, or the model ignored good context. Debugging means reproducing the request locally and adding print statements, and the bug may not reproduce at all.

Cost has the same problem. The invoice says $40k. Was that the summarization feature, one tenant's batch job, or an agent loop that ran 200 steps?

## How It Works

<pre class="mermaid">
flowchart TD
    R["request (trace root)"] --> RT["retrieve"]
    RT --> E["embed"]
    RT --> V["vector_search · k=20"]
    RT --> RR["rerank"]
    R --> P["build_prompt"]
    R --> L["llm · model, input_tokens,<br/>output_tokens, cost_usd"]
    R --> G["guardrail"]
</pre>

1. **Open a root span per request,** and a child span for each step. Parent links come from context propagation, so async and threaded steps attach to the right parent.
2. **Use a fixed vocabulary of span names.** `llm`, `retrieve` and `tool` are names. The user ID, the query and the tool's arguments are *attributes*. A span name per query is the classic way to wreck a tracing backend.
3. **Record what you'll query later:** tokens, cost, model, k, number of chunks kept, cache hit or miss, the error on the span that failed.
4. **Hash or redact text by default.** Prompts contain whatever users typed. Keep raw text only in a sampled, access-controlled store.
5. **Roll up by span name** to see where time and money go across thousands of requests, not just in one trace.

## When to Use It

- You run anything with more than one step: RAG, agents, chains, guardrails.
- Someone asks "why was this slow?", "why did this cost so much?" or "what did the model actually see?"
- You're about to optimize, and want to know which step to optimize.

## When NOT to Use It

- **One model call, no pipeline.** Request-level logs from your gateway are enough.
- **Throwaway prototypes.** Add tracing when the pipeline shape settles. Most frameworks can auto-instrument later.

Note that "too much volume" isn't on this list. The answer to volume is sampling, not skipping tracing.

## Trade-offs

- **Storage.** A RAG request produces 5–15 spans, and an agent run can produce hundreds. Use head sampling for routine traffic, and always keep error traces and slow outliers.
- **Privacy.** Tracing backends are often third-party SaaS. Decide deliberately what text, if any, leaves your network.
- **Instrumentation drift.** Someone adds a step and doesn't add a span, and the trace now has an unexplained gap. Auto-instrumentation from your framework or gateway reduces this risk.

## Failure Modes

**Orphaned async spans.** Parallel tool calls or worker threads start spans without the parent context, so they show up as separate traces and the parent looks mysteriously fast. Propagate context explicitly into executors and test a parallel path.

**Cardinality explosion.** Span names include IDs, and the backend's index or bill grows without limit. Enforce the name vocabulary in code, as the example does.

**PII in the trace backend.** Full prompts are logged "temporarily for debugging" and stay there for 13 months. Redact or hash by default, and make raw-text capture an explicit, sampled opt-in.

## Implementation Example

A dependency-free tracer with context-propagated parents, a fixed span-name vocabulary, hashed sensitive attributes, errors recorded on the span that raised, and roll-ups by span name. In production, use OpenTelemetry. This shows what it's doing for you.

```bash
cd examples && pytest observability_and_evaluation/test_span_level_tracing.py
```

<!-- example: examples/observability_and_evaluation/span_level_tracing.py -->
```python
"""Span-Level Tracing.

One trace per request, one span per pipeline step, with tokens and cost on the
model spans. Parent/child links come from a context variable, so nested and
async steps attach to the right parent without passing span objects around.

In production use OpenTelemetry with the GenAI semantic conventions; this is
the same shape with no dependencies, so you can see what the SDK is doing.
"""

from __future__ import annotations

import contextvars
import hashlib
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

# Span *names* must come from a fixed set. Put variable things (user id, query)
# in attributes; a span name per query makes every dashboard useless.
SPAN_NAMES = {"request", "retrieve", "embed", "vector_search", "rerank", "build_prompt", "llm", "tool", "guardrail"}
SENSITIVE_ATTRS = {"prompt", "completion", "query", "user_input"}


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_id: str | None
    name: str
    start: float
    end: float = 0.0
    attributes: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def duration_s(self) -> float:
        return self.end - self.start


_current: contextvars.ContextVar[Span | None] = contextvars.ContextVar("current_span", default=None)


class Tracer:
    def __init__(self, clock: Callable[[], float] = time.monotonic, keep_raw_text: bool = False):
        self.clock = clock
        self.keep_raw_text = keep_raw_text  # off by default: traces get shipped to third parties
        self.finished: list[Span] = []

    @contextmanager
    def span(self, name: str, **attributes) -> Iterator[Span]:
        if name not in SPAN_NAMES:
            raise ValueError(f"unknown span name {name!r}; add it to SPAN_NAMES deliberately")
        parent = _current.get()
        span = Span(
            trace_id=parent.trace_id if parent else uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            parent_id=parent.span_id if parent else None,
            name=name,
            start=self.clock(),
        )
        self.set(span, **attributes)
        token = _current.set(span)
        try:
            yield span
        except Exception as exc:
            span.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            span.end = self.clock()
            _current.reset(token)
            self.finished.append(span)

    def set(self, span: Span, **attributes) -> None:
        for key, value in attributes.items():
            if key in SENSITIVE_ATTRS and not self.keep_raw_text:
                text = str(value)
                span.attributes[f"{key}.sha256"] = hashlib.sha256(text.encode()).hexdigest()[:16]
                span.attributes[f"{key}.chars"] = len(text)
            else:
                span.attributes[key] = value

    # ---- the questions you actually ask of traces ----

    def tree(self, trace_id: str) -> list[tuple[int, Span]]:
        spans = [s for s in self.finished if s.trace_id == trace_id]
        children = defaultdict(list)
        for s in spans:
            children[s.parent_id].append(s)
        out: list[tuple[int, Span]] = []

        def walk(parent_id, depth):
            for s in sorted(children[parent_id], key=lambda s: s.start):
                out.append((depth, s))
                walk(s.span_id, depth + 1)

        walk(None, 0)
        return out

    def rollup(self) -> dict[str, dict[str, float]]:
        """Total time, tokens and cost per span name, across all traces."""
        totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for s in self.finished:
            t = totals[s.name]
            t["count"] += 1
            t["seconds"] += s.duration_s
            t["tokens"] += s.attributes.get("input_tokens", 0) + s.attributes.get("output_tokens", 0)
            t["cost_usd"] += s.attributes.get("cost_usd", 0.0)
            t["errors"] += 1 if s.error else 0
        return {k: dict(v) for k, v in totals.items()}
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| OpenTelemetry + GenAI semantic conventions | The vendor-neutral standard; export anywhere |
| OpenLLMetry, OpenInference | OTel instrumentation for LLM SDKs and frameworks |
| Langfuse, Arize Phoenix | Open-source LLM tracing UIs with cost and eval views |
| LangSmith, Braintrust, Datadog LLM Observability | Managed platforms |

## Related Patterns

- [LLM Gateway](../inference-and-serving/llm-gateway.md) emits the model-call spans for every service.
- [LLM-as-Judge](llm-as-judge.md) scores can be attached to traces, so you can go from a low score to the exact trace that caused it.
- [Multi-Agent Orchestration](../inference-and-serving/multi-agent-orchestration.md) is close to impossible to debug without spans that link workers to the plan.
- [Guardrails](../security-and-trust/guardrails.md) should record their verdicts as spans so blocks are auditable.

## Further Reading

- [OpenTelemetry semantic conventions for generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [OpenTelemetry: Traces](https://opentelemetry.io/docs/concepts/signals/traces/)
- [Langfuse tracing documentation](https://langfuse.com/docs/tracing)
