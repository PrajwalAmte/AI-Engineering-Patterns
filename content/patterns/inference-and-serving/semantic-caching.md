---
title: Semantic Caching
pillar: inference-and-serving
status: validated-in-production
tags: [caching, cost, latency, embeddings]
related:
  - LLM Gateway
  - Model Router
  - Retrieval Freshness Watermark
  - Context Compaction
example: examples/inference_and_serving/semantic_caching.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Answer a query from cache when it means the same as one you've already answered, and stop near-misses from serving the wrong answer.
sidebar:
  order: 3
---

## What It Is

A cache keyed by meaning instead of exact text. Each incoming query is embedded and compared with the queries already in the cache. If one is close enough, its stored answer is returned without calling the model.

The idea is simple. The hard part is the edge cases: two questions that embed close together but need different answers, and cached answers that were right last week and are wrong today.

## The Problem It Solves

Exact-match caching barely helps with natural language. "What's your return policy?", "how do returns work" and "can I send this back?" are the same question, but they share no cache key. On support and FAQ-style workloads a large share of traffic is rephrasings of a small set of questions, and each one pays full model cost and latency.

## How It Works

<pre class="mermaid">
flowchart TD
    Q["Query + system prompt + tenant"] --> K["Scope key<br/>hash(tenant, system prompt)"]
    Q --> E["Embed query"]
    K & E --> L{"Nearest cached query<br/>in the same scope ≥ threshold?"}
    L -->|"hit"| H["Return cached answer"]
    L -->|"miss"| M["Call model"]
    M --> C{"Answer worth caching?"}
    C -->|"yes"| S["Store with TTL + source doc IDs"]
    C -->|"no"| R["Return without caching"]
    S --> R
    D["Doc updated in ingestion"] -.->|"invalidate entries citing it"| S
</pre>

1. **Scope first.** Only compare against entries with the same tenant and system prompt. The same words under a different persona, or for a different customer, are a different question.
2. **Embed and search.** Find the nearest cached query in that scope. Return its answer if the similarity is at or above the threshold.
3. **On a miss, call the model** and store the answer only if it passes a quality check. Caching a refusal or an empty answer turns one bad response into hundreds.
4. **Expire and invalidate.** Every entry has a TTL. Entries also record which source documents they were built from, so the ingestion pipeline can evict them when those documents change.
5. **Watch the hit rate.** A sudden drop usually means the embedding model or the prompt template changed.

## When to Use It

- Support bots, FAQ assistants, internal help desks: anywhere people keep asking the same few things.
- Answers that stay correct for hours or days.
- Cost or latency on repeated questions is a real problem.

## When NOT to Use It

- **Answers depend on live state.** Order status, prices or inventory need fresh data. Cache the retrieval layer, not the final answer.
- **Every request is unique.** Code generation or creative prompts with distinct specs will barely hit, and you still pay for an embedding on every request.
- **Answers are personalized.** If the answer depends on who's asking, the user has to be part of the scope key, and then the hit rate collapses.

## Trade-offs

- **The threshold is a precision/recall dial with no safe default.** Too strict and you never hit. Too loose and "cancel my subscription" matches "cancel my order". Tune it on labelled pairs from your own traffic, not on a number from a blog post (including this one).
- **Staleness is guaranteed.** A cache serves old answers by design. TTLs and source-based invalidation keep that within bounds, but they don't remove it.
- **Every query pays for an embedding,** hit or miss. That's cheap next to a large model, but less so next to a small one.

## Failure Modes

**Near-miss answers.** Two queries embed close together and want different answers: "can I cancel my flight" and "can I cancel my subscription", or "is X compatible with Y" and "is X compatible with Z". Users get a confident answer to a question they didn't ask, and it's hard to reproduce because it depends on what's in the cache. Raise the threshold for short queries, where one word carries most of the meaning, and log the matched cached query next to every hit so you can audit them.

**Serving stale facts.** The refund window changes from 30 days to 14. Half your users get the new answer and half get the cached one, depending on how they phrased it. Tag entries with their source documents and invalidate when ingestion sees a change.

**Hit rate falls to zero.** Someone upgrades the embedding model, or edits the system prompt, which changes every scope key. The cache is now pure overhead. Alert on hit rate, and treat both kinds of change as a cache migration.

## Implementation Example

A scoped, TTL'd semantic cache with source invalidation and a quality gate on writes. The tests use a toy bag-of-words embedder so they run offline. In production, pass your real embedding function and back `entries` with a vector index.

```bash
cd examples && pytest inference_and_serving/test_semantic_caching.py
```

<!-- example: examples/inference_and_serving/semantic_caching.py -->
```python
"""Semantic Caching.

Serve a cached answer when a new query means the same thing as an old one.
The similarity threshold is only half the safety story: entries are also
scoped (same system prompt, same tenant), expire, and can be invalidated when
the documents they were built from change.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field

Embed = Callable[[str], list[float]]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


@dataclass
class Entry:
    query: str
    vector: list[float]
    answer: str
    scope: str
    sources: frozenset[str]
    expires_at: float


@dataclass
class SemanticCache:
    embed: Embed
    threshold: float = 0.92  # tune per workload against labelled near-duplicate pairs
    ttl_s: float = 3600.0
    max_entries: int = 10_000
    clock: Callable[[], float] = time.monotonic
    entries: list[Entry] = field(default_factory=list)
    hits: int = 0
    misses: int = 0

    @staticmethod
    def scope_key(system_prompt: str, tenant: str) -> str:
        # Two identical questions under different system prompts are different questions.
        return hashlib.sha256(f"{tenant}\x00{system_prompt}".encode()).hexdigest()[:16]

    def lookup(self, query: str, scope: str) -> str | None:
        now = self.clock()
        self.entries = [e for e in self.entries if e.expires_at > now]
        vector = self.embed(query)
        best, best_sim = None, self.threshold
        for entry in self.entries:
            if entry.scope != scope:
                continue
            sim = _cosine(vector, entry.vector)
            if sim >= best_sim:
                best, best_sim = entry, sim
        if best is None:
            self.misses += 1
            return None
        self.hits += 1
        return best.answer

    def store(self, query: str, answer: str, scope: str, sources: set[str] = frozenset()) -> None:
        if len(self.entries) >= self.max_entries:
            self.entries.pop(0)  # oldest first; good enough when TTLs do most of the eviction
        self.entries.append(
            Entry(query, self.embed(query), answer, scope, frozenset(sources), self.clock() + self.ttl_s)
        )

    def invalidate_source(self, source_id: str) -> int:
        """Call from your ingestion pipeline when a document changes."""
        before = len(self.entries)
        self.entries = [e for e in self.entries if source_id not in e.sources]
        return before - len(self.entries)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


def cached_complete(
    cache: SemanticCache,
    llm: Callable[[str], str],
    query: str,
    system_prompt: str,
    tenant: str,
    cacheable: Callable[[str], bool] = lambda answer: bool(answer.strip()),
) -> tuple[str, bool]:
    """Returns (answer, was_cache_hit). Only answers that pass `cacheable` are stored."""
    scope = cache.scope_key(system_prompt, tenant)
    hit = cache.lookup(query, scope)
    if hit is not None:
        return hit, True
    answer = llm(f"{system_prompt}\n\n{query}")
    if cacheable(answer):
        cache.store(query, answer, scope)
    return answer, False
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| GPTCache | Open-source library dedicated to semantic caching |
| Redis (vector search) / RedisVL | `SemanticCache` class; a good fit if Redis is already in your stack |
| LiteLLM, Portkey | Semantic caching at the gateway, configured rather than coded |
| Any vector DB (Qdrant, pgvector, …) | Store query embeddings next to answers; you write the policy |

## Related Patterns

- [LLM Gateway](llm-gateway.md) is where the cache usually lives, so every caller benefits.
- [Model Router](model-router.md) runs after the cache. A hit never reaches the router.
- [Retrieval Freshness Watermark](../retrieval-and-memory/retrieval-freshness-watermark.md) tackles the same staleness problem one layer down.
- [Context Compaction](../cost-and-efficiency/context-compaction.md) cuts the cost of the misses.

## Further Reading

- [GPTCache](https://github.com/zilliztech/GPTCache), Zilliz
- [RedisVL semantic caching guide](https://docs.redisvl.com/en/latest/user_guide/03_llmcache.html)
