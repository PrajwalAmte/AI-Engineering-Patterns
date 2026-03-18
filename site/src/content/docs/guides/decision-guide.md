---
title: Decision Guide
description: Answer questions about your AI system to get recommended patterns.
---

Use this guide to identify which patterns are most relevant to your current situation. Start with the question that best describes your primary concern.

## I need to reduce costs

**How are you currently calling LLMs?**

- Direct API calls with no intermediary → Start with [LLM Gateway Pattern](/patterns/inference-and-serving/llm-gateway/)
- Single provider, single model for everything → Start with [Model Router Pattern](/patterns/inference-and-serving/model-router/)
- Seeing many repeated or similar queries → Start with [Semantic Caching](/patterns/inference-and-serving/semantic-caching/)
- Long context windows eating your budget → Start with [Prompt Compression Pattern](/patterns/cost-and-efficiency/prompt-compression/)
- No visibility into per-feature spend → Start with [Cost Attribution Pattern](/patterns/observability/cost-attribution/)

## I need to improve reliability

**What kind of failures are you seeing?**

- Provider outages causing downtime → Start with [Fallback Chain](/patterns/inference-and-serving/fallback-chain/) and [Circuit Breaker for LLMs](/patterns/reliability/circuit-breaker/)
- Quality degradation after prompt or model changes → Start with [Prompt Regression Guard](/patterns/reliability/prompt-regression-guard/)
- Silent quality drops nobody notices → Start with [Quality Drift Detection](/patterns/observability/quality-drift-detection/)
- No safe way to roll out model changes → Start with [Canary Deployment for Models](/patterns/reliability/canary-deployment/)

## I need better retrieval / RAG

**What does your knowledge base look like?**

- Static documents, FAQ-style → [Classic RAG Pattern](/patterns/retrieval-and-memory/classic-rag/)
- Complex relational data, multi-hop questions → [GraphRAG Pattern](/patterns/retrieval-and-memory/graph-rag/)
- Need both keyword and semantic matching → [Hybrid Search Pattern](/patterns/retrieval-and-memory/hybrid-search/)
- Retrieval quality is inconsistent → [Reranking Pattern](/patterns/retrieval-and-memory/reranking/)
- Need to remember across user sessions → [Contextual Memory Pattern](/patterns/retrieval-and-memory/contextual-memory/)

## I need to handle security and compliance

**What is your primary concern?**

- Prompt injection and jailbreak attempts → [Input Sanitization Pattern](/patterns/security-and-trust/input-sanitization/)
- PII in model inputs or outputs → [PII Scrubbing Pipeline](/patterns/security-and-trust/pii-scrubbing/)
- Need structured, type-safe outputs → [Structured Output Enforcement](/patterns/security-and-trust/structured-output-enforcement/)
- Audit requirements for model interactions → [Audit Trail Pattern](/patterns/security-and-trust/audit-trail/)
- Regulatory compliance (EU AI Act, HIPAA) → [Policy-as-Code Pattern](/patterns/governance/policy-as-code/)

## I need observability

**What can you not see today?**

- What is happening inside multi-step chains → [Span-Level Tracing Pattern](/patterns/observability/span-level-tracing/)
- How much each feature or user costs → [Cost Attribution Pattern](/patterns/observability/cost-attribution/)
- Whether output quality is changing over time → [Quality Drift Detection](/patterns/observability/quality-drift-detection/)
- How to set meaningful SLAs → [SLO Pattern for AI](/patterns/observability/slo-for-ai/)

## I am building agent systems

Agents combine multiple patterns. A typical production agent stack includes:

1. [LLM Gateway Pattern](/patterns/inference-and-serving/llm-gateway/) for routing and observability
2. [Least-Privilege Tool Access](/patterns/security-and-trust/least-privilege-tool-access/) for safe tool use
3. [Agent Action Log Pattern](/patterns/governance/agent-action-log/) for auditability
4. [Human-in-the-Loop Gate](/patterns/governance/human-in-the-loop/) for high-risk actions
5. [Cost Circuit Breaker](/patterns/cost-and-efficiency/cost-circuit-breaker/) for runaway prevention
6. [Contextual Memory Pattern](/patterns/retrieval-and-memory/contextual-memory/) for session persistence
