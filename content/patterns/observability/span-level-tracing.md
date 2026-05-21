---
title: Span-Level Tracing
pillar: observability
status: validated-in-production
tags: [observability, tracing, latency, debugging]
related:
  - Cost Attribution Pattern
  - Quality Drift Detection
  - Prompt Logging Pattern
  - LLM Gateway Pattern
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Trace every step of an AI pipeline with latency and token counts per span for debugging and optimization.
sidebar:
  order: 1
---

## What It Is

Span-level tracing decomposes every AI pipeline execution into individual spans — retrieval, prompt construction, inference, tool calls, postprocessing — each tagged with timing, token counts, cost, and metadata. It extends OpenTelemetry-style distributed tracing to the specific operations that matter in AI systems.

## The Problem It Solves

When an AI pipeline returns a slow or bad response, the first question is "which step broke?" Without span-level tracing:

- You know total latency but not whether the bottleneck is retrieval, prompt assembly, or inference.
- You know total token count but not how many tokens went to context vs. instructions vs. output.
- You know the final output but not what retrieved context or intermediate reasoning led to it.
- Debugging requires adding print statements, reproducing the issue, and manually stepping through the pipeline.

Traditional APM tools instrument HTTP calls and database queries. They do not instrument prompt construction, retrieval scoring, or token consumption — the operations that dominate AI pipeline performance.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Request received"] --> B["Start trace"]
    B --> C["Span: input validation"]
    C --> D["Span: retrieval"]
    D --> D1["Child span: embedding"]
    D --> D2["Child span: vector search"]
    D --> D3["Child span: reranking"]
    D3 --> E["Span: prompt construction"]
    E --> F["Span: inference (latency, tokens, cost)"]
    F --> G["Span: output validation"]
    G --> H["Export trace to backend"]
    H --> I["Dashboards, queries, and alerts"]
</pre>

1. Each pipeline execution creates a trace with a unique ID.
2. Every significant operation within the pipeline creates a child span.
3. Spans capture operation-specific attributes: token counts for embedding calls, result counts for retrieval, model name and cost for inference.
4. Spans are nested to show parent-child relationships.
5. Completed traces are exported to a trace backend for visualization, querying, and alerting.
6. Aggregated span metrics enable identifying systemic bottlenecks across many requests.

## When to Use It

- You are running multi-step AI pipelines (RAG, agents, chains) and need to understand per-step performance.
- Latency or cost debugging requires more granularity than request-level metrics provide.
- You need to answer questions like "why was this response slow?" or "which step consumed the most tokens?"
- You are optimizing pipeline performance and need data on where time and tokens are actually spent.

## When not to Use It

- Your AI integration is a single, direct LLM API call with no pipeline. A single API call does not benefit from span-level decomposition. Request-level metrics are sufficient.
- You are in early prototyping where the pipeline changes daily. Instrumentation code becomes maintenance overhead that slows iteration. Add tracing when the pipeline stabilizes.
- Your trace backend cannot handle the volume. Each request generates multiple spans. At high throughput, consider sampling rather than skipping tracing entirely.

## Trade-offs

1. **Instrumentation overhead** — Adding span creation and attribute recording to every pipeline step adds code and a small latency overhead (typically sub-millisecond per span).
2. **Storage costs** — Traces are verbose. A single RAG pipeline execution can generate 5-15 spans. At 10,000 requests/day, that is 50,000-150,000 spans/day. Sampling strategies are essential at scale.
3. **Schema maintenance** — As the pipeline evolves, span names and attributes must be kept consistent. Stale or renamed spans create gaps in dashboards and alerts.
4. **Privacy considerations** — Traces may capture prompt content and model outputs. Ensure sensitive data is redacted before export to the trace backend.

## Failure Modes

### Span Cardinality Explosion
**Trigger**: Dynamic span names (e.g., including user IDs, query text, or tool names in span identifiers) create unbounded unique span types.
**Symptom**: Trace backend storage costs spike. Dashboards become unusable because every span is "unique." Aggregation and alerting break because there are no stable span groups to monitor.
**Mitigation**: Enforce a fixed span name taxonomy in code (e.g., `retrieve`, `generate`, `rerank`). Pass dynamic values as span attributes, not span names.

### Missing Spans on Async or Parallel Steps
**Trigger**: Pipeline steps that run in parallel (async retrieval, concurrent tool calls) are not properly linked to the parent trace context.
**Symptom**: Traces show gaps — the parent span completes but child spans are either missing or appear as orphaned root spans. Latency analysis underreports actual work.
**Mitigation**: Explicitly propagate trace context into async workers and thread pools. Test tracing specifically for parallel pipeline paths.

### PII Leakage in Trace Attributes
**Trigger**: Span attributes include full prompt text or user queries without redaction, and traces are exported to a shared or third-party backend.
**Symptom**: Sensitive user data is visible in trace dashboards accessible to multiple teams or stored in a third-party service, violating privacy policies.
**Mitigation**: Apply a redaction filter in the trace exporter pipeline. Only store prompt hashes or truncated previews by default. Full content should require explicit opt-in with access controls.

## Implementation Example

```python
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: uuid4().hex[:16])
    parent_id: str | None = None
    start_time: float = 0.0
    end_time: float = 0.0
    attributes: dict = field(default_factory=dict)
    children: list["Span"] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000


class Tracer:
    def __init__(self):
        self._traces: dict[str, Span] = {}

    @contextmanager
    def start_trace(self, name: str):
        trace_id = uuid4().hex[:32]
        root = Span(name=name, trace_id=trace_id)
        root.start_time = time.monotonic()
        self._traces[trace_id] = root
        ctx = _TraceContext(root_span=root, current_span=root)
        try:
            yield ctx
        finally:
            root.end_time = time.monotonic()

    def get_trace(self, trace_id: str) -> Span | None:
        return self._traces.get(trace_id)


class _TraceContext:
    def __init__(self, root_span: Span, current_span: Span):
        self.root_span = root_span
        self._current = current_span

    @contextmanager
    def span(self, name: str, **attributes):
        child = Span(
            name=name,
            trace_id=self.root_span.trace_id,
            parent_id=self._current.span_id,
            attributes=attributes,
        )
        child.start_time = time.monotonic()
        self._current.children.append(child)
        previous = self._current
        self._current = child
        try:
            yield child
        finally:
            child.end_time = time.monotonic()
            self._current = previous

    def set_attribute(self, key: str, value) -> None:
        self._current.attributes[key] = value


def format_trace(span: Span, indent: int = 0) -> str:
    prefix = "  " * indent
    line = f"{prefix}{span.name}: {span.duration_ms:.1f}ms"
    if span.attributes:
        attrs = ", ".join(f"{k}={v}" for k, v in span.attributes.items())
        line += f" ({attrs})"
    lines = [line]
    for child in span.children:
        lines.append(format_trace(child, indent + 1))
    return "\n".join(lines)


async def traced_rag_pipeline(tracer: Tracer, query: str) -> dict:
    with tracer.start_trace("rag_pipeline") as ctx:
        ctx.set_attribute("query", query)

        with ctx.span("retrieval") as retrieval_span:
            with ctx.span("embedding", model="text-embedding-3-small"):
                query_embedding = await embed(query)
                ctx.set_attribute("tokens", len(query.split()))

            with ctx.span("vector_search"):
                results = await search(query_embedding, top_k=20)
                ctx.set_attribute("candidates", len(results))

            with ctx.span("reranking"):
                reranked = await rerank(query, results, top_k=5)
                ctx.set_attribute("selected", len(reranked))

        with ctx.span("prompt_construction"):
            prompt = build_prompt(query, reranked)
            ctx.set_attribute("token_count", count_tokens(prompt))

        with ctx.span("inference", model="claude-3-5-sonnet") as llm_span:
            response = await generate(prompt)
            ctx.set_attribute("input_tokens", response["usage"]["input_tokens"])
            ctx.set_attribute("output_tokens", response["usage"]["output_tokens"])

        with ctx.span("output_validation"):
            validated = validate_output(response)
            ctx.set_attribute("passed", validated)

        return response
```

For production use, integrate with OpenTelemetry SDKs instead of a custom implementation. The example demonstrates the concept; real systems should use established tracing infrastructure.

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| Langfuse | Open-source LLM observability | Purpose-built for LLM tracing with cost tracking and evaluation |
| Arize Phoenix | Open-source | LLM traces with embedding drift detection |
| Langsmith | Managed (LangChain) | Deep integration with LangChain, traces chain executions |
| Helicone | Managed proxy | Request-level tracing at the gateway, less granular than span-level |
| OpenTelemetry + Jaeger | Open-source infrastructure | Generic tracing adapted for AI with custom span attributes |
| Datadog LLM Observability | Managed APM | Extends existing Datadog with LLM-specific spans |

## Related Patterns

- **[Cost Attribution Pattern](/AI-Engineering-Patterns/patterns/observability/cost-attribution/)** — Uses span-level token and cost data to attribute spend per feature and user.
- **[Quality Drift Detection](/AI-Engineering-Patterns/patterns/observability/quality-drift-detection/)** — Aggregates quality signals from traced outputs over time.
- **[Prompt Logging Pattern](/AI-Engineering-Patterns/patterns/observability/prompt-logging/)** — Span attributes can include prompt content for debugging. Balance with privacy.
- **[LLM Gateway Pattern](/AI-Engineering-Patterns/patterns/inference-and-serving/llm-gateway/)** — The gateway produces the inference span. Pipeline tracing wraps around it.

## Further Reading

- [Langfuse Tracing Documentation](https://langfuse.com/docs/tracing)
- [OpenTelemetry for LLMs — Arize AI](https://docs.arize.com/phoenix/tracing/llm-traces)
- [Distributed Tracing — OpenTelemetry Concepts](https://opentelemetry.io/docs/concepts/signals/traces/)
