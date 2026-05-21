---
title: Decision Guide
description: Answer questions about your AI system to get recommended patterns.
---

Use this guide to identify which patterns are most relevant to your current situation. Start with the question that best describes your primary concern.

## I need to reduce costs

**How are you currently calling LLMs?**

- Direct API calls with no intermediary → Start with [LLM Gateway Pattern](/AI-Engineering-Patterns/patterns/inference-and-serving/llm-gateway/)
- Single provider, single model for everything → Start with [Model Router Pattern](/AI-Engineering-Patterns/patterns/inference-and-serving/model-router/)
- Seeing many repeated or similar queries → Start with [Semantic Caching](/AI-Engineering-Patterns/patterns/inference-and-serving/semantic-caching/)
- Long context windows eating your budget → Start with [Token Budget Pattern](/AI-Engineering-Patterns/patterns/cost-and-efficiency/token-budget/)
- Most queries are simple but you pay for maximum context on every request → Start with [Cascading Context Assembly](/AI-Engineering-Patterns/patterns/cost-and-efficiency/cascading-context-assembly/)

## I need to improve reliability

**What kind of failures are you seeing?**

- Provider outages causing downtime → Start with [Circuit Breaker for LLMs](/AI-Engineering-Patterns/patterns/reliability/circuit-breaker/)
- Quality degradation after prompt changes → Start with [Prompt Canary Deployment](/AI-Engineering-Patterns/patterns/governance/prompt-canary-deployment/) and [LLM-as-Judge](/AI-Engineering-Patterns/patterns/evaluation-and-testing/llm-as-judge/)
- Silent quality drops nobody notices → Start with [Embedding Drift Detector](/AI-Engineering-Patterns/patterns/observability/embedding-drift-detector/) and [Span-Level Tracing](/AI-Engineering-Patterns/patterns/observability/span-level-tracing/)

## I need better retrieval / RAG

**What does your knowledge base look like?**

- Complex relational data, multi-hop questions → [GraphRAG Pattern](/AI-Engineering-Patterns/patterns/graph-patterns/graph-rag/)
- Need both keyword and semantic matching → [Hybrid Search Pattern](/AI-Engineering-Patterns/patterns/retrieval-and-memory/hybrid-search/)
- Retrieval returns stale or outdated content → [Retrieval Freshness Watermark](/AI-Engineering-Patterns/patterns/retrieval-and-memory/retrieval-freshness-watermark/)
- Retrieval returns redundant/duplicate chunks → [Semantic Deduplication](/AI-Engineering-Patterns/patterns/data-patterns/semantic-deduplication/)
- Upstream data keeps breaking your pipeline → [Data Contract Pattern](/AI-Engineering-Patterns/patterns/data-patterns/data-contract/)

## I need to handle security and compliance

**What is your primary concern?**

- Prompt injection and jailbreak attempts → [Input Sanitization Pattern](/AI-Engineering-Patterns/patterns/security-and-trust/input-sanitization/)
- Agents calling external tools that return untrusted data → [Tool Output Firewall](/AI-Engineering-Patterns/patterns/security-and-trust/tool-output-firewall/)
- Need standardized model documentation for compliance → [Model Card Pattern](/AI-Engineering-Patterns/patterns/governance/model-card/)

## I need observability

**What can you not see today?**

- What is happening inside multi-step chains → [Span-Level Tracing Pattern](/AI-Engineering-Patterns/patterns/observability/span-level-tracing/)
- Whether retrieval quality is silently degrading → [Embedding Drift Detector](/AI-Engineering-Patterns/patterns/observability/embedding-drift-detector/)

## I am building agent systems

Agents combine multiple patterns. A typical production agent stack includes:

1. [LLM Gateway Pattern](/AI-Engineering-Patterns/patterns/inference-and-serving/llm-gateway/) for routing and observability
2. [Input Sanitization](/AI-Engineering-Patterns/patterns/security-and-trust/input-sanitization/) for the front door
3. [Tool Output Firewall](/AI-Engineering-Patterns/patterns/security-and-trust/tool-output-firewall/) for the side door (tool results re-entering context)
4. [Circuit Breaker for LLMs](/AI-Engineering-Patterns/patterns/reliability/circuit-breaker/) for provider resilience
5. [Token Budget Pattern](/AI-Engineering-Patterns/patterns/cost-and-efficiency/token-budget/) for runaway prevention
6. [Span-Level Tracing](/AI-Engineering-Patterns/patterns/observability/span-level-tracing/) for debugging multi-step flows

## I need graph-based intelligence

**What are you trying to achieve with graphs?**

- Multi-hop questions that connect information across documents → Start with [GraphRAG](/AI-Engineering-Patterns/patterns/graph-patterns/graph-rag/)
- Non-linear reasoning with branching and merging approaches → Start with [Graph of Thoughts](/AI-Engineering-Patterns/patterns/graph-patterns/graph-of-thoughts/)
- Deduplicating entities across multiple data sources → Start with [Entity Resolution Graph](/AI-Engineering-Patterns/patterns/graph-patterns/entity-resolution-graph/)
- Building a knowledge graph for your domain → Start with [GraphRAG](/AI-Engineering-Patterns/patterns/graph-patterns/graph-rag/) for the retrieval layer and [Entity Resolution Graph](/AI-Engineering-Patterns/patterns/graph-patterns/entity-resolution-graph/) for clean entity data

## I need to evaluate and test AI quality

**What is your primary evaluation challenge?**

- Need automated quality scoring at scale → Start with [LLM-as-Judge](/AI-Engineering-Patterns/patterns/evaluation-and-testing/llm-as-judge/)
- Quality is degrading after prompt or model changes → Combine [LLM-as-Judge](/AI-Engineering-Patterns/patterns/evaluation-and-testing/llm-as-judge/) with [Prompt Canary Deployment](/AI-Engineering-Patterns/patterns/governance/prompt-canary-deployment/)
- Need a quality gate before deploying prompt changes → Use [Prompt Canary Deployment](/AI-Engineering-Patterns/patterns/governance/prompt-canary-deployment/) with [LLM-as-Judge](/AI-Engineering-Patterns/patterns/evaluation-and-testing/llm-as-judge/) as the scoring mechanism
