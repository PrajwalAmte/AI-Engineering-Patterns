---
title: Semantic Deduplication
pillar: data-patterns
status: emerging
tags: [data-quality, deduplication, embeddings, rag, indexing]
related:
  - Data Contract
  - Hybrid Search
  - Embedding Drift Detector
  - Retrieval Freshness Watermark
example: examples/data_patterns/semantic_deduplication.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Collapse chunks that say the same thing before indexing, so the retriever doesn't give the model the same answer five times, without merging chunks that differ in a number.
sidebar:
  order: 2
---

## What It Is

Before chunks go into the retrieval index, group the ones that say the same thing in different words, keep one canonical chunk per group, and record what was merged into what. Exact-match and near-duplicate methods (hashing, MinHash) catch copies. Semantic deduplication uses embeddings to catch rewrites.

Pretraining pipelines have deduplicated web data at this level for years. The RAG version is less established, hence "emerging".

## The Problem It Solves

Real knowledge bases repeat themselves. The password reset steps are in the wiki, the FAQ, the onboarding guide and three old support macros. Each is worded slightly differently, and all of them are indexed.

When a user asks how to reset their password, four of your five retrieval slots go to the same answer. The fifth, which held the SSO caveat that actually applied to this user, never makes it in. Redundant chunks don't just waste tokens. They push out the different information the model needed.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Chunks from all sources"] --> E["Embed<br/>(same model as retrieval)"]
    E --> N["Neighbours above threshold"]
    N --> G{"Same numbers / key facts?"}
    G -->|"no"| K["Keep separate"]
    G -->|"yes"| U["Same cluster"]
    U --> C["Pick canonical:<br/>source authority → newest → most complete"]
    C --> I["Index canonical chunks"]
    C --> M["Store merge map<br/>(dropped id → canonical id)"]
</pre>

1. **Embed with the retrieval model.** Duplicates in a different embedding space aren't the duplicates your retriever sees.
2. **Find neighbours** above a high similarity threshold. Use ANN search at scale. The example compares all pairs for clarity.
3. **Guard the merge.** Never merge chunks whose numbers differ. "Shipping takes 5 days" and "shipping takes 10 days" embed almost the same and mean different things. Extend the guard to named entities, jurisdictions and versions where they matter in your domain.
4. **Choose a canonical chunk** per cluster by a rule you can explain: the most authoritative source first, then the newest, then the most complete.
5. **Keep the merge map.** When someone asks "why isn't the FAQ answer showing up?", you can say which chunk replaced it.

## When to Use It

- The corpus combines several sources that cover the same topics.
- You've seen retrieval results where most of the top-k say the same thing.
- Context slots are scarce, and the diversity of retrieved chunks matters.

## When NOT to Use It

- **One well-maintained source** where every document is unique by construction.
- **Near-identical documents that differ in ways that matter legally:** contract variants, regional policies, versioned specs. The number guard helps, but think hard before deduplicating these at all.
- **Query-time diversity is enough.** Maximal Marginal Relevance (MMR) at retrieval time also reduces redundancy, with no index changes. Try it first if your corpus is small.

## Trade-offs

- **The threshold cuts both ways.** Set it too low and you merge things that are related but different. Set it too high and you miss obvious rewrites. Label a few hundred pairs from your own corpus and pick the threshold from those.
- **The canonical chunk isn't always the best one for every query.** The short FAQ version wins the cluster, and a detailed question needed the long version. The merge map lets you fall back to it.
- **Incremental runs drift.** New chunks join old clusters one at a time, and clusters slowly take in looser and looser matches. Re-run deduplication from scratch on a schedule.

## Failure Modes

**Merging documents that differ in one critical detail.** Two regional policies differ by one number or one country name. Without a guard, one of them disappears, and users in the other region get the wrong answer. Number and entity guards are cheap, so always use them.

**Changing the embedding model invalidates the clusters.** After an embedding upgrade, yesterday's clusters no longer match what the retriever sees. Re-run deduplication as part of the re-indexing job.

**The canonical chunk is stale.** The rule picked the most authoritative source, which hasn't been updated in two years. Combine authority with freshness, using the dates from a [Retrieval Freshness Watermark](../retrieval-and-memory/retrieval-freshness-watermark.md).

## Implementation Example

Threshold clustering with union-find, a number guard against false merges, explainable canonical selection, and a merge map. The tests include the case that has to fail: two shipping policies that differ only in their numbers.

```bash
cd examples && pytest data_patterns/test_semantic_deduplication.py
```

<!-- example: examples/data_patterns/semantic_deduplication.py -->
```python
"""Semantic Deduplication.

Before indexing, group chunks that say the same thing and keep one canonical
chunk per group. Two guards stop it from merging things that only *look*
alike: chunks whose numbers differ are never merged, and the merge map is kept
so you can always find what was dropped and why.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

NUMBERS = re.compile(r"\d+(?:[.,]\d+)*")


@dataclass
class Doc:
    id: str
    text: str
    source: str
    updated: date


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / ((sum(x * x for x in a) ** 0.5 or 1.0) * (sum(y * y for y in b) ** 0.5 or 1.0))


def _same_facts(a: str, b: str) -> bool:
    # "Pro costs $49" and "Pro costs $59" embed almost identically. Never merge those.
    return set(NUMBERS.findall(a)) == set(NUMBERS.findall(b))


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def deduplicate(
    docs: list[Doc],
    embed: Callable[[str], list[float]],
    threshold: float = 0.95,
    source_rank: dict[str, int] | None = None,  # lower = more authoritative
) -> tuple[list[Doc], dict[str, str]]:
    """Returns (canonical docs, merged_id -> canonical_id)."""
    vectors = [embed(d.text) for d in docs]
    uf = _UnionFind(len(docs))
    # O(n²) for clarity. At scale, only compare each doc to its ANN neighbours.
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            if _cosine(vectors[i], vectors[j]) >= threshold and _same_facts(docs[i].text, docs[j].text):
                uf.union(i, j)

    clusters: dict[int, list[Doc]] = {}
    for i, doc in enumerate(docs):
        clusters.setdefault(uf.find(i), []).append(doc)

    ranks = source_rank or {}

    def preference(d: Doc):
        return (ranks.get(d.source, 99), -d.updated.toordinal(), -len(d.text))

    canonical, merged = [], {}
    for members in clusters.values():
        keep = min(members, key=preference)
        canonical.append(keep)
        for d in members:
            if d is not keep:
                merged[d.id] = keep.id
    return canonical, merged
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| datasketch (MinHash LSH) | Fast near-duplicate detection; use it first to remove literal copies cheaply |
| NVIDIA NeMo Curator | Exact, fuzzy and semantic deduplication pipelines for large corpora |
| Any vector DB | Query-before-insert: look up neighbours of each new chunk before adding it |
| LangChain / LlamaIndex | MMR retrieval for query-time diversity |

## Related Patterns

- [Data Contract](data-contract.md) runs first. Deduplicate clean data, not malformed data.
- [Hybrid Search](../retrieval-and-memory/hybrid-search.md) returns more distinct results from a deduplicated index.
- [Embedding Drift Detector](../observability-and-evaluation/embedding-drift-detector.md): when the embedding space shifts, re-run deduplication.
- [Retrieval Freshness Watermark](../retrieval-and-memory/retrieval-freshness-watermark.md) supplies the dates used to choose the canonical chunk.

## Further Reading

- [SemDeDup: Data-efficient learning at web-scale through semantic deduplication](https://arxiv.org/abs/2303.09540), Abbas et al., 2023
- [Deduplicating Training Data Makes Language Models Better](https://arxiv.org/abs/2107.06499), Lee et al., 2021
- [D4: Improving LLM Pretraining via Document De-Duplication and Diversification](https://arxiv.org/abs/2308.12284), Tirumala et al., 2023
