---
title: Decision Guide
description: Start from the problem you have today and find the two or three patterns worth reading first.
---

Nobody needs all 37 patterns. Find the problem that sounds most like yours below, read the patterns it points to, and run their examples. Each one is a single `pytest` command.

## "Our LLM bill is too high"

Measure before you optimize. Put an [LLM Gateway](../patterns/inference-and-serving/llm-gateway.md) in front of your model calls so you know which feature is spending what. Then:

- **The same questions keep coming in** → [Semantic Caching](../patterns/inference-and-serving/semantic-caching.md)
- **Everything goes to the flagship model** → [Model Router](../patterns/inference-and-serving/model-router.md)
- **Every request sends maximum context** → [Cascading Context Assembly](../patterns/cost-and-efficiency/cascading-context-assembly.md), then [Token Budget](../patterns/cost-and-efficiency/token-budget.md)
- **Agents use 40 tool calls on simple questions** → [Effort Scaling](../patterns/cost-and-efficiency/effort-scaling.md)
- **Long agent sessions get slower and pricier with every step** → [Context Compaction](../patterns/cost-and-efficiency/context-compaction.md)

## "The provider had a bad day and so did we"

- **Sustained degradation: errors, slow or empty answers** → [Circuit Breaker for LLMs](../patterns/reliability/circuit-breaker.md)
- **Most requests are fine, but p99 is awful** → [Request Hedging for LLMs](../patterns/reliability/request-hedging.md)
- **Answers come back successfully but unsure or incomplete** → [Uncertainty-Triggered Retry](../patterns/reliability/uncertainty-triggered-retry.md)

## "The RAG answers are wrong"

Work through these in order. Each one fixes a different layer.

1. **The right document isn't retrieved** (exact terms, IDs, error codes) → [Hybrid Search](../patterns/retrieval-and-memory/hybrid-search.md)
2. **Irrelevant chunks get in, or the bot answers when it should say "I don't know"** → [Retrieval Quality Gate](../patterns/retrieval-and-memory/retrieval-quality-gate.md)
3. **Old versions of documents win** → [Retrieval Freshness Watermark](../patterns/retrieval-and-memory/retrieval-freshness-watermark.md)
4. **The top-5 results all say the same thing** → [Semantic Deduplication](../patterns/data-patterns/semantic-deduplication.md)
5. **Good context, but the answer adds details that aren't in it** → [Grounding Verifier](../patterns/retrieval-and-memory/grounding-verifier.md)
6. **The question is about relationships** ("who owns what depends on X") → [GraphRAG](../patterns/graph-patterns/graph-rag.md), with [Entity Resolution Graph](../patterns/graph-patterns/entity-resolution-graph.md) to keep the graph clean
7. **Upstream data keeps changing shape under you** → [Data Contract](../patterns/data-patterns/data-contract.md)

## "We changed a prompt and something broke"

- **Before merging:** [Prompt Mutation Testing](../patterns/observability-and-evaluation/prompt-mutation-testing.md) checks robustness, and [LLM-as-Judge](../patterns/observability-and-evaluation/llm-as-judge.md) runs the regression suite.
- **Before users see it:** [Shadow Model Evaluation](../patterns/observability-and-evaluation/shadow-model-evaluation.md) runs it on real traffic with zero exposure.
- **While rolling out:** [Prompt Canary Deployment](../patterns/governance/prompt-canary-deployment.md) uses staged rollout with automatic rollback.

## "We can't see what's going on"

- **Why was this request slow, expensive or wrong?** → [Span-Level Tracing](../patterns/observability-and-evaluation/span-level-tracing.md)
- **Is retrieval quietly getting worse?** → [Embedding Drift Detector](../patterns/observability-and-evaluation/embedding-drift-detector.md)
- **Is quality going up or down this week?** → [LLM-as-Judge](../patterns/observability-and-evaluation/llm-as-judge.md) on sampled traffic

## "We're building agents"

A reasonable starting stack, in the order you'll need it:

1. [Loop Termination](../patterns/loop-engineering/loop-termination.md): every loop needs a stop rule before it needs anything else.
2. [Guardrails](../patterns/security-and-trust/guardrails.md) with a tool policy: decide what the agent may do *in code*.
3. [Human-in-the-Loop](../patterns/governance/human-in-the-loop.md) for anything irreversible.
4. [Tool Output Firewall](../patterns/security-and-trust/tool-output-firewall.md) as soon as the agent reads web pages, emails or user-written data.
5. [Span-Level Tracing](../patterns/observability-and-evaluation/span-level-tracing.md), because you can't debug agents without it.
6. [Context Compaction](../patterns/cost-and-efficiency/context-compaction.md) once sessions get long.

When agents start doing real work unattended:

- **They say "done" when they aren't** → [Maker–Verifier Split](../patterns/loop-engineering/maker-verifier-split.md)
- **They repeat the same mistake** → [Reflexion Loop](../patterns/loop-engineering/reflexion-loop.md), plus [No-Progress Detection](../patterns/loop-engineering/no-progress-detection.md)
- **They fail at step 7 of 10 and start over** → [Semantic Rollback](../patterns/loop-engineering/semantic-rollback.md)
- **One agent's context isn't enough for the task** → [Multi-Agent Orchestration](../patterns/inference-and-serving/multi-agent-orchestration.md) (read its "When NOT to use it" first)
- **Partial answers from different attempts could be combined** → [Graph of Thoughts](../patterns/graph-patterns/graph-of-thoughts.md)

## "Security or compliance is asking questions"

- **Prompt injection, PII in prompts** → [Input Sanitization](../patterns/security-and-trust/input-sanitization.md). Read its honest limits, then [Guardrails](../patterns/security-and-trust/guardrails.md).
- **"What is this system for, and how was it tested?"** → [Model Card](../patterns/governance/model-card.md)
- **"Who approved that action?"** → [Human-in-the-Loop](../patterns/governance/human-in-the-loop.md)

## "Long conversations go off the rails"

- **The bot forgets what the user said earlier** → [Sliding Context Window with Memory Consolidation](../patterns/retrieval-and-memory/sliding-context-window.md)
- **Agent transcripts fill the window with tool output** → [Context Compaction](../patterns/cost-and-efficiency/context-compaction.md)
