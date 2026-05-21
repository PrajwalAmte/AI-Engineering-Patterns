---
title: Getting Started
description: How to use AI Engineering Patterns and find the right patterns for your system.
---

AI Engineering Patterns is a structured pattern library for engineers building AI systems in production. It is not an awesome list of links, not vendor documentation, and not a research paper collection. It is a curated set of named patterns with descriptions, trade-offs, when-to-use guides, and code examples for every layer of a production AI system.

## How to Use This Resource

### If you know what you are looking for

Browse the sidebar. Patterns are organized into 8 pillars. Each pillar covers a distinct layer of a production AI system.

### If you are not sure where to start

Use the [Decision Guide](/AI-Engineering-Patterns/guides/decision-guide/) to answer a few questions about your system and get recommended patterns.

### If you want to understand the landscape

Read through the pillars in order. They roughly follow the lifecycle of a request through a production AI system:

1. **Inference & Serving** — How requests reach models and how responses come back.
2. **Data Patterns for AI** — The data foundation every AI system depends on.
3. **Reliability & Resilience** — Keeping AI systems working when things go wrong.
4. **Retrieval & Memory** — What knowledge AI systems can access and remember.
5. **Observability & Monitoring** — Seeing what your AI system is actually doing.
6. **Security & Trust** — Guardrails, PII handling, and prompt injection defenses.
7. **Cost & Efficiency** — Running AI systems without unbounded spend.
8. **Governance & Compliance** — Lineage, model cards, and compliance operations.
9. **Graph Patterns** — Knowledge graphs, graph-based reasoning, and entity resolution.
10. **Evaluation & Testing** — LLM-as-Judge, eval pipelines, and regression testing.

## Reading a Pattern

Every pattern follows the same structure:

| Section | Purpose |
|---|---|
| What It Is | One paragraph plain-language description |
| The Problem It Solves | What breaks without this pattern |
| How It Works | Step-by-step mechanism with diagrams |
| When to Use It | Specific conditions and workload types |
| When not to Use It | Explicit anti-use-cases |
| Trade-offs | 2-4 honest trade-offs |
| Failure Modes | What breaks when the pattern is deployed correctly — trigger, symptom, mitigation |
| Implementation Example | Minimal working code snippet |
| Tool Landscape | Tools that implement or support the pattern |
| Related Patterns | Links to adjacent patterns |
| Further Reading | 2-4 high-quality external references |

The **When not to Use It** section is the most important. It is what makes this resource opinionated rather than encyclopedic.

## Pattern Maturity

Each pattern has a status indicating its maturity level:

- **Proposed** — Pattern identified, not yet validated in production systems.
- **Emerging** — Used by early adopters, trade-offs still being understood.
- **Validated in Production** — Widely used by multiple teams, trade-offs well understood.

## Contributing

This is an open-source project. If you have used a pattern in production and want to share it, or if you see something that needs correction, see the [Contributing Guide](https://github.com/PrajwalAmte/AI-Engineering-Patterns/blob/main/CONTRIBUTING.md).
