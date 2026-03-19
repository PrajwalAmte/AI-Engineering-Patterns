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
- Long context windows eating your budget → Start with [Prompt Compression Pattern](/AI-Engineering-Patterns/patterns/cost-and-efficiency/prompt-compression/)
- No visibility into per-feature spend → Start with [Cost Attribution Pattern](/AI-Engineering-Patterns/patterns/observability/cost-attribution/)

## I need to improve reliability

**What kind of failures are you seeing?**

- Provider outages causing downtime → Start with [Fallback Chain](/AI-Engineering-Patterns/patterns/inference-and-serving/fallback-chain/) and [Circuit Breaker for LLMs](/AI-Engineering-Patterns/patterns/reliability/circuit-breaker/)
- Quality degradation after prompt or model changes → Start with [Prompt Regression Guard](/AI-Engineering-Patterns/patterns/reliability/prompt-regression-guard/)
- Silent quality drops nobody notices → Start with [Quality Drift Detection](/AI-Engineering-Patterns/patterns/observability/quality-drift-detection/)
- No safe way to roll out model changes → Start with [Canary Deployment for Models](/AI-Engineering-Patterns/patterns/reliability/canary-deployment/)

## I need better retrieval / RAG

**What does your knowledge base look like?**

- Static documents, FAQ-style → [Classic RAG Pattern](/AI-Engineering-Patterns/patterns/retrieval-and-memory/classic-rag/)
- Complex relational data, multi-hop questions → [GraphRAG Pattern](/AI-Engineering-Patterns/patterns/retrieval-and-memory/graph-rag/)
- Need both keyword and semantic matching → [Hybrid Search Pattern](/AI-Engineering-Patterns/patterns/retrieval-and-memory/hybrid-search/)
- Retrieval quality is inconsistent → [Reranking Pattern](/AI-Engineering-Patterns/patterns/retrieval-and-memory/reranking/)
- Need to remember across user sessions → [Contextual Memory Pattern](/AI-Engineering-Patterns/patterns/retrieval-and-memory/contextual-memory/)

## I need to handle security and compliance

**What is your primary concern?**

- Prompt injection and jailbreak attempts → [Input Sanitization Pattern](/AI-Engineering-Patterns/patterns/security-and-trust/input-sanitization/)
- PII in model inputs or outputs → [PII Scrubbing Pipeline](/AI-Engineering-Patterns/patterns/security-and-trust/pii-scrubbing/)
- Need structured, type-safe outputs → [Structured Output Enforcement](/AI-Engineering-Patterns/patterns/security-and-trust/structured-output-enforcement/)
- Audit requirements for model interactions → [Audit Trail Pattern](/AI-Engineering-Patterns/patterns/security-and-trust/audit-trail/)
- Regulatory compliance (EU AI Act, HIPAA) → [Policy-as-Code Pattern](/AI-Engineering-Patterns/patterns/governance/policy-as-code/)

## I need observability

**What can you not see today?**

- What is happening inside multi-step chains → [Span-Level Tracing Pattern](/AI-Engineering-Patterns/patterns/observability/span-level-tracing/)
- How much each feature or user costs → [Cost Attribution Pattern](/AI-Engineering-Patterns/patterns/observability/cost-attribution/)
- Whether output quality is changing over time → [Quality Drift Detection](/AI-Engineering-Patterns/patterns/observability/quality-drift-detection/)
- How to set meaningful SLAs → [SLO Pattern for AI](/AI-Engineering-Patterns/patterns/observability/slo-for-ai/)

## I am building agent systems

Agents combine multiple patterns. A typical production agent stack includes:

1. [LLM Gateway Pattern](/AI-Engineering-Patterns/patterns/inference-and-serving/llm-gateway/) for routing and observability
2. [Least-Privilege Tool Access](/AI-Engineering-Patterns/patterns/security-and-trust/least-privilege-tool-access/) for safe tool use
3. [Agent Action Log Pattern](/AI-Engineering-Patterns/patterns/governance/agent-action-log/) for auditability
4. [Human-in-the-Loop Gate](/AI-Engineering-Patterns/patterns/governance/human-in-the-loop/) for high-risk actions
5. [Cost Circuit Breaker](/AI-Engineering-Patterns/patterns/cost-and-efficiency/cost-circuit-breaker/) for runaway prevention
6. [Contextual Memory Pattern](/AI-Engineering-Patterns/patterns/retrieval-and-memory/contextual-memory/) for session persistence

## I need graph-based intelligence

**What are you trying to achieve with graphs?**

- Multi-hop questions that connect information across documents → Start with [GraphRAG](/AI-Engineering-Patterns/patterns/graph-patterns/graph-rag/)
- Non-linear reasoning with branching and merging approaches → Start with [Graph of Thoughts](/AI-Engineering-Patterns/patterns/graph-patterns/graph-of-thoughts/)
- Deduplicating entities across multiple data sources → Start with [Entity Resolution Graph](/AI-Engineering-Patterns/patterns/graph-patterns/entity-resolution-graph/)
- Building a knowledge graph for your domain → Start with [GraphRAG](/AI-Engineering-Patterns/patterns/graph-patterns/graph-rag/) for the retrieval layer and [Entity Resolution Graph](/AI-Engineering-Patterns/patterns/graph-patterns/entity-resolution-graph/) for clean entity data

## I need to evaluate and test AI quality

**What is your primary evaluation challenge?**

- Need automated quality scoring at scale → Start with [LLM-as-Judge](/AI-Engineering-Patterns/patterns/evaluation-and-testing/llm-as-judge/)
- Quality is degrading after prompt or model changes → Combine [LLM-as-Judge](/AI-Engineering-Patterns/patterns/evaluation-and-testing/llm-as-judge/) with [Span-Level Tracing](/AI-Engineering-Patterns/patterns/observability/span-level-tracing/)
- Need a quality gate before deploying changes → Build an eval pipeline with [LLM-as-Judge](/AI-Engineering-Patterns/patterns/evaluation-and-testing/llm-as-judge/) scoring
