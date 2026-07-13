---
title: Semantic Caching
pillar: inference-and-serving
status: validated-in-production
tags: [caching, cost, latency, embeddings]
related:
  - LLM Gateway Pattern
  - Model Router Pattern
  - Prompt Compression Pattern
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Cache LLM responses by meaning rather than exact text match, serving similar queries from cache for 40-60% cost reduction.
sidebar:
  order: 3
---

## What It Is

Semantic caching stores LLM responses indexed by the meaning of the query rather than the exact string. When a new query arrives, its embedding is compared against cached query embeddings. If a sufficiently similar query exists in the cache, the cached response is returned without making an LLM call.

## The Problem It Solves

Traditional exact-match caching misses the vast majority of cache opportunities in LLM workloads. Users phrase the same question in dozens of different ways. "What's your return policy?" and "How do I return an item?" are semantically identical but share no cache key in a string-match system. Without semantic caching, every rephrasing triggers a full inference call at full cost and latency.

## How It Works

<pre class="mermaid">
flowchart TD
A["Query arrives"] --> B["Generate embedding"]
B --> C{"Search cache\n(cosine similarity)"}
C -->|"Hit (sim ≥ threshold)"| D["Return cached response"]
C -->|"Miss"| E["Call LLM"]
E --> F["Cache response with TTL"]
F --> G["Return response"]
</pre>

1. A new query arrives and is converted to an embedding vector using a lightweight embedding model.
2. The embedding is compared against all cached query embeddings using cosine similarity (or approximate nearest neighbor search).
3. If any cached query has similarity above the configured threshold (typically 0.92-0.97), the cached response is returned.
4. On a cache miss, the query is sent to the LLM. The response, along with the query embedding, is stored in the cache with a TTL.
5. Cache entries expire based on TTL or are evicted using LRU when the cache reaches capacity.

## When to Use It

- Customer support or FAQ workloads where users ask similar questions repeatedly.
- Internal tools where the same types of queries recur across users.
- Any workload with high query repetition and tolerance for slightly stale answers.
- Cost reduction is a priority and sub-second latency is desirable for common queries.

## When not to Use It

- Queries depend on real-time data that changes between requests (stock prices, live inventory). Cached responses will be stale and wrong.
- Every query is genuinely unique (code generation with different specifications, creative writing with unique prompts). Hit rates will be near zero, and you pay the embedding cost on every request for no benefit.
- The system prompt or context changes frequently per request. Two queries may be textually similar but have different system prompts, making cached responses incorrect.
- You need deterministic, auditable responses where every interaction must be independently generated and logged.

## Trade-offs

1. **Embedding cost** — Every query requires an embedding call even on cache hits. For very cheap models, the embedding cost can approach the inference cost, reducing the net savings.
2. **Similarity threshold tuning** — Too high and you miss valid cache hits. Too low and you serve wrong answers for different-enough queries. Requires monitoring and adjustment per workload.
3. **Stale responses** — Cached answers may be outdated if the underlying knowledge changes. TTL must be tuned to the data freshness requirements.
4. **Cache poisoning** — A low-quality response that gets cached will be served to many users. Consider caching only responses that pass quality checks.

## Failure Modes

### Semantic False Match
**Trigger**: Two queries are semantically similar according to embeddings but require different answers ("cancel my subscription" vs. "can I cancel my flight?").
**Symptom**: Users receive cached answers meant for a different intent. Complaints about wrong answers that are hard to reproduce because they depend on cache state.
**Mitigation**: Include system prompt hash and key context variables in the cache key — not just query similarity. Add a minimum exact-token-overlap threshold alongside cosine similarity.

### Stale Cache Serving Outdated Facts
**Trigger**: Underlying knowledge changes (product price, policy update) but cached responses still contain old information.
**Symptom**: Users get confidently delivered wrong facts. The issue is intermittent — some users get the cache hit, others get fresh (correct) responses.
**Mitigation**: Set TTLs based on content volatility. Implement cache invalidation hooks tied to knowledge base updates. Tag cached entries with source document versions.

### Cache Hit Rate Collapse
**Trigger**: Embedding model update, prompt template change, or system prompt modification shifts the embedding space.
**Symptom**: Cache hit rate drops to near zero overnight. Costs spike because every query goes to the LLM. The cache becomes pure overhead.
**Mitigation**: Monitor hit rate as a key metric with alerting threshold. On embedding model changes, warm the cache with historical queries or accept a grace period.

## Implementation Example

```python
import hashlib
import json
import time
from dataclasses import dataclass

import numpy as np


@dataclass
class CacheEntry:
    query_embedding: np.ndarray
    response: dict
    created_at: float
    ttl: float


class SemanticCache:
    def __init__(self, similarity_threshold: float = 0.95, default_ttl: float = 3600):
        self._entries: list[CacheEntry] = []
        self._threshold = similarity_threshold
        self._default_ttl = default_ttl

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        dot = np.dot(a, b)
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        if norm == 0:
            return 0.0
        return float(dot / norm)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        self._entries = [
            e for e in self._entries if (now - e.created_at) < e.ttl
        ]

    def lookup(self, query_embedding: np.ndarray) -> dict | None:
        self._evict_expired()
        best_similarity = 0.0
        best_entry = None

        for entry in self._entries:
            sim = self._cosine_similarity(query_embedding, entry.query_embedding)
            if sim > best_similarity:
                best_similarity = sim
                best_entry = entry

        if best_entry and best_similarity >= self._threshold:
            return best_entry.response
        return None

    def store(
        self, query_embedding: np.ndarray, response: dict, ttl: float | None = None
    ) -> None:
        self._entries.append(
            CacheEntry(
                query_embedding=query_embedding,
                response=response,
                created_at=time.monotonic(),
                ttl=ttl or self._default_ttl,
            )
        )


async def cached_completion(
    cache: SemanticCache,
    embed_fn,
    llm_fn,
    query: str,
    **kwargs,
) -> dict:
    query_embedding = await embed_fn(query)
    cached = cache.lookup(query_embedding)
    if cached is not None:
        return cached

    response = await llm_fn(query, **kwargs)
    cache.store(query_embedding, response)
    return response
```

For production use, replace the in-memory list with a vector database (Redis with vector search, Qdrant, or Pinecone) to support persistence, distributed access, and approximate nearest neighbor search at scale.

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| GPTCache | Open-source library | Purpose-built semantic cache for LLM applications |
| Redis + RediSearch | Infrastructure | Vector similarity search on top of Redis, good for existing Redis users |
| Qdrant | Vector database | Can serve as both a retrieval store and semantic cache |
| Portkey | Managed gateway | Built-in semantic caching at the gateway layer |
| Momento | Managed cache | Serverless caching with vector search support |

## Related Patterns

- **[LLM Gateway Pattern](/AI-Engineering-Patterns/patterns/inference-and-serving/llm-gateway/)** — The gateway is the natural integration point for semantic caching.
- **[Model Router Pattern](/AI-Engineering-Patterns/patterns/inference-and-serving/model-router/)** — Routing decisions happen before cache lookup in the request pipeline.
- **[Prompt Compression Pattern](/AI-Engineering-Patterns/patterns/cost-and-efficiency/prompt-compression/)** — Another cost reduction pattern. Can be combined: compress, then cache.
- **[Cost Attribution Pattern](/AI-Engineering-Patterns/patterns/observability/cost-attribution/)** — Track cache hit rates per feature to measure cost savings.

## Further Reading

- [GPTCache: An Open-Source Semantic Cache for LLM Applications](https://github.com/zilliztech/GPTCache)
- [Semantic Caching for GenAI — Redis Technical Blog](https://redis.io/blog/semantic-caching-for-genai/)
- [Caching Strategies for LLM Applications — Langchain Documentation](https://python.langchain.com/docs/integrations/llm_caching/)
