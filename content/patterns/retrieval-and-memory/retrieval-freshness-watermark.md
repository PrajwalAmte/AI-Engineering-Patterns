---
title: Retrieval Freshness Watermark
pillar: retrieval-and-memory
status: emerging
tags: [retrieval, rag, freshness, metadata, temporal]
related:
  - Hybrid Search
  - Data Contract
  - Semantic Caching
  - Grounding Verifier
example: examples/retrieval_and_memory/retrieval_freshness_watermark.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Store when each chunk's content became true, drop superseded versions, and show the model how old each source is so it can say so.
sidebar:
  order: 2
---

## What It Is

Every chunk in the index carries an *effective date*: when its content became true, not when it was crawled. At query time, three things happen. Older versions of a document are dropped when a newer one was retrieved. Age is blended into the ranking for questions about the present. And each chunk goes into the prompt with an "as of" line, so the model can say "as of March, the price was…" instead of stating an old fact as current.

"Watermark" is our name for this metadata, not an industry term. The underlying ideas (temporal metadata, recency boosting, version de-duplication) are common practice in search.

## The Problem It Solves

Embedding similarity has no notion of time. The pricing page from 2024 and the one from last week are almost the same text, so they score almost the same, and the older one sometimes wins. The model then states the old price confidently, because nothing in the prompt says it might be out of date.

It gets worse when both versions are retrieved. The model sees "refunds within 30 days" and "refunds within 14 days" with nothing to choose between them, and either picks one or blends them into something neither page says.

## How It Works

<pre class="mermaid">
flowchart TD
    I["Ingestion"] --> M["Extract effective date<br/>(not crawl time)"]
    M --> X["Index chunk + doc_key + effective date + content type"]
    Q["Query + retrieved candidates"] --> V["Drop revoked chunks;<br/>keep newest version per doc_key"]
    V --> T{"Time-sensitive query?"}
    T -->|"yes"| W["Blend: α·similarity + (1−α)·freshness"]
    T -->|"no"| N["Mostly similarity"]
    W & N --> P["Prompt: [n] (as of DATE, N days old) text"]
</pre>

1. **At ingestion, record the effective date.** Use an "effective as of" date or the publication date from the content itself. Fall back to last-modified. Crawl time is a last resort, and those chunks should be flagged.
2. **Give every logical document a stable `doc_key`** so its versions can be recognized as the same document.
3. **At query time, keep only the newest version of each document,** and never serve chunks that were explicitly revoked.
4. **Blend freshness into the score only when the query is about the present** ("current", "latest", prices). Freshness decays per content type: news goes stale in weeks, pricing in months, policies in years. A floor keeps old but still valid content in the running.
5. **Show the dates to the model** and tell it to prefer newer sources and to say when its newest source is old.

## When to Use It

- The corpus has content that changes: pricing, policies, product specs, regulations, org charts.
- Old versions stay in the index (wikis, document stores, ticket history).
- Users ask "current", "latest" or "now" questions and act on the answers.

## When NOT to Use It

- **Static reference material.** Proofs, historical records and textbooks don't decay.
- **The index only ever holds the current version,** because ingestion deletes on update. Then the problem doesn't exist. (This is also a good fix, if you can manage it.)
- **You already filter by date** in the retrieval query. You still need the "as of" lines in the prompt, but you can skip the rest.

## Trade-offs

- **Dates are messy.** Many documents have no reliable date, or contain several. A wrong date is worse than none, because it gives false confidence.
- **Freshness can push out the best answer.** Boost recency too much and a newer, less relevant chunk wins. That's why the blend only applies to time-sensitive queries, and why the example's α still weights similarity most.
- **More configuration.** Half-lives per content type are judgment calls that someone has to own.

## Failure Modes

**Crawl date mistaken for content date.** A 2019 PDF is ingested today and treated as brand new. Validate dates at ingestion: a content date years older than the crawl date is normal, but no content date at all should be flagged.

**One recency weight for every query.** "How does TLS work" gets penalized for citing a good 2019 explainer, and "current price of Pro" doesn't get enough boost. Detect time-sensitive queries, even with a regex, and only boost those.

**Decay cliff.** An exponential decay with no floor sends a three-year-old but still valid policy to zero, and it disappears. Keep "old" (still valid, ranks lower) separate from "revoked" (never served).

## Implementation Example

Version de-duplication, revocation, per-type decay with a floor, a query-sensitive blend, and the "as of" prompt format. The tests include the case that motivated the pattern: an outdated price that is *more* similar to the query than the current one.

```bash
cd examples && pytest retrieval_and_memory/test_retrieval_freshness_watermark.py
```

<!-- example: examples/retrieval_and_memory/retrieval_freshness_watermark.py -->
```python
"""Retrieval Freshness Watermark.

Every chunk carries the date its content was effective, not the date it was
indexed. At query time: superseded versions are dropped, freshness is blended
into the score only for time-sensitive queries, and each chunk goes into the
prompt with an "as of" line so the model can say how current its answer is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# How long until a chunk is "half as fresh", by content type. These are
# starting points to argue about, not constants of nature.
HALF_LIFE_DAYS = {"pricing": 90, "news": 14, "policy": 365, "reference": 3650}
FRESHNESS_FLOOR = 0.2  # old-but-unrevoked content still competes
TIME_SENSITIVE = re.compile(r"\b(current|currently|latest|now|today|this (week|month|year)|price|pricing|cost)\b", re.I)


@dataclass
class Chunk:
    doc_key: str  # stable id of the logical document, shared across versions
    text: str
    effective: date  # when this content became true, NOT when it was indexed
    content_type: str = "reference"
    expired: bool = False  # explicitly revoked: never served


def freshness(chunk: Chunk, today: date) -> float:
    age = max((today - chunk.effective).days, 0)
    half_life = HALF_LIFE_DAYS.get(chunk.content_type, 365)
    return max(FRESHNESS_FLOOR, 0.5 ** (age / half_life))


def rank(
    query: str,
    candidates: list[tuple[Chunk, float]],  # (chunk, similarity) from your retriever
    today: date,
    k: int = 4,
) -> list[tuple[Chunk, float]]:
    # 1. Revoked content is gone; of several versions of one document, keep the newest.
    newest: dict[str, tuple[Chunk, float]] = {}
    for chunk, sim in candidates:
        if chunk.expired:
            continue
        held = newest.get(chunk.doc_key)
        if held is None or chunk.effective > held[0].effective:
            newest[chunk.doc_key] = (chunk, sim)

    # 2. Only let age move the ranking when the question is about the present.
    alpha = 0.6 if TIME_SENSITIVE.search(query) else 0.95
    scored = [(c, alpha * sim + (1 - alpha) * freshness(c, today)) for c, sim in newest.values()]
    return sorted(scored, key=lambda pair: -pair[1])[:k]


def build_context(ranked: list[tuple[Chunk, float]], today: date) -> str:
    lines = [
        f"Today is {today.isoformat()}. Each source shows the date it was effective.",
        "If sources conflict, prefer the more recent one. If the newest relevant source is old,",
        "say how old it is instead of presenting it as current.",
        "",
    ]
    for i, (chunk, _) in enumerate(ranked, start=1):
        age = (today - chunk.effective).days
        lines.append(f"[{i}] (as of {chunk.effective.isoformat()}, {age} days old) {chunk.text}")
    return "\n".join(lines)
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Vespa | Freshness and recency as first-class ranking features |
| Elasticsearch / OpenSearch | `function_score` with date decay functions (gauss, exp, linear) |
| Weaviate, Qdrant, Pinecone | Metadata filters on date fields; blend scores in your own code |
| LlamaIndex | Recency postprocessors over node metadata |

## Related Patterns

- [Hybrid Search](hybrid-search.md) produces the candidates this pattern re-ranks.
- [Data Contract](../data-patterns/data-contract.md) is where you require ingestion sources to provide a reliable effective date.
- [Semantic Caching](../inference-and-serving/semantic-caching.md) has the same staleness problem one layer up. Align cache TTLs with content half-lives.
- [Grounding Verifier](grounding-verifier.md) confirms an answer matches its sources. This pattern makes sure those sources are current.

## Further Reading

- [Elasticsearch function_score decay functions](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-function-score-query.html#function-decay)
- [Vespa ranking with freshness](https://docs.vespa.ai/en/reference/rank-features.html#freshness)
