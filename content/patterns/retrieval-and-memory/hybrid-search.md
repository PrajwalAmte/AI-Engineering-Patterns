---
title: Hybrid Search
pillar: retrieval-and-memory
status: validated-in-production
tags: [retrieval, rag, search, embeddings, bm25]
related:
  - Retrieval Quality Gate
  - Retrieval Freshness Watermark
  - GraphRAG
  - Grounding Verifier
example: examples/retrieval_and_memory/hybrid_search.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Run keyword (BM25) and vector search side by side and merge the rankings, so exact identifiers and paraphrases both get found.
sidebar:
  order: 1
---

## What It Is

Two retrievers run on every query. BM25 or another keyword index finds documents that contain the query's exact terms. A vector index finds documents that mean something similar. The two ranked lists are merged, usually with Reciprocal Rank Fusion (RRF), and the merged top-k goes on to the next stage.

If you're building RAG and haven't decided on a retriever, this is the sensible default.

## The Problem It Solves

Each retriever fails on a different kind of query.

Embeddings are bad at exact strings. A support engineer pastes `E-4012` and the vector search returns documents about payment errors in general, maybe including `E-4013`, because to an embedding model those look almost identical. The same goes for SKUs, function names, version numbers and people's names.

Keyword search is bad at paraphrase. "Authentication issues" won't match a page titled "Resolving login failures" because they share no words.

Real traffic contains both kinds of query, often from the same user in the same session.

## How It Works

<pre class="mermaid">
flowchart LR
    Q["Query"] --> S["BM25 / keyword index"]
    Q --> D["Embed → vector index"]
    S --> SR["Ranked list A"]
    D --> DR["Ranked list B<br/>(below similarity floor dropped)"]
    SR & DR --> F["Reciprocal Rank Fusion"]
    F --> T["Top-k → reranker / gate / prompt"]
</pre>

1. Send the query to both indexes in parallel and take the top 20–50 candidates from each.
2. Drop dense results below a minimum similarity. Vector search always returns *something*, even for a query with no good match.
3. Merge with RRF. Each document scores the sum, over the lists it appears in, of 1 / (k + rank). The constant k (60 is the usual value, from the original paper) flattens the advantage of being ranked first.

$$\text{RRF}(d) = \sum_{r \in R} \frac{1}{k + \text{rank}_r(d)}$$

4. Pass the fused top-k to a reranker or a [Retrieval Quality Gate](retrieval-quality-gate.md).

RRF uses ranks, not scores, so you never have to put a BM25 score and a cosine similarity on the same scale. That's most of why it's the default.

## When to Use It

- Your corpus has identifiers alongside prose: error codes, product names, API names, ticket numbers.
- Queries come from a mix of experts (who type exact terms) and everyone else (who describe the problem).
- You're setting a RAG baseline. Hybrid plus a reranker is hard to beat without domain-specific work.

## When NOT to Use It

- **Pure prose, no jargon.** Dense retrieval alone may be enough. Measure it on your own eval set before adding a second index.
- **Tiny corpora.** With a few hundred documents, you can often skip retrieval and put everything in the context.
- **You can't keep two indexes in sync.** Two pipelines that drift apart are worse than one good pipeline. Many engines (Elasticsearch/OpenSearch, Weaviate, Qdrant, Vespa, Postgres with pgvector plus FTS) do both in one store, which removes most of this concern.

## Trade-offs

- **Two indexes to build and update.** Every document change has to land in both.
- **Fusion weighting is per domain.** Plain RRF treats both lists equally. If one side is consistently better for your traffic, a weighted fusion or a learned reranker will do better.
- **A good reranker narrows the gap.** With a strong cross-encoder on top, the lift from hybrid over dense-only shrinks. It rarely disappears, because the reranker can only re-order candidates that some retriever found in the first place.

## Failure Modes

**The two indexes disagree.** The vector index was rebuilt last night and the keyword index last week. One document now appears in only one list, under a different version. Write to both from one ingestion pipeline, and store a content version on every chunk so you can detect this.

**One side floods the fusion.** An ambiguous one-word query ("python") brings back plausible-looking junk from one retriever, and it fills half the top-k. Per-retriever floors (the dense similarity cutoff in the example) and a downstream gate stop junk from reaching the prompt.

**Tokenizer eats identifiers.** The keyword analyzer splits `E-4012` into `e` and `4012`, and now every error code matches every other error code. Check how your analyzer tokenizes your real identifiers before trusting BM25 with them.

## Implementation Example

A pure-Python BM25, a dense index over any embedding function, and RRF. The tests check the two halves separately: an identifier query is won by BM25, and a paraphrase query is won by the dense side.

```bash
cd examples && pytest retrieval_and_memory/test_hybrid_search.py
```

<!-- example: examples/retrieval_and_memory/hybrid_search.py -->
```python
"""Hybrid Search: BM25 + dense retrieval, merged with Reciprocal Rank Fusion.

BM25 finds the exact error code; embeddings find the paraphrase. RRF merges
the two rankings without having to make their scores comparable.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

Embed = Callable[[str], list[float]]
_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-_.]*", re.I)


def tokenize(text: str) -> list[str]:
    # Keep identifiers like "E-4012" and "v2.3.1" whole; they are why BM25 is here.
    return [t.lower().strip(".") for t in _TOKEN.findall(text)]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [tokenize(d) for d in docs]
        self.avg_len = sum(map(len, self.docs)) / max(len(self.docs), 1)
        df = Counter(term for doc in self.docs for term in set(doc))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        out = []
        for doc in self.docs:
            tf = Counter(doc)
            norm = self.k1 * (1 - self.b + self.b * len(doc) / self.avg_len)
            out.append(sum(self.idf.get(t, 0.0) * tf[t] * (self.k1 + 1) / (tf[t] + norm) for t in terms if tf[t]))
        return out


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / ((sum(x * x for x in a) ** 0.5 or 1.0) * (sum(y * y for y in b) ** 0.5 or 1.0))


def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion: score(d) = sum over lists of 1 / (k + rank)."""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return fused


@dataclass
class Hit:
    doc_id: int
    text: str
    score: float
    sparse_rank: int | None
    dense_rank: int | None


class HybridIndex:
    def __init__(self, docs: list[str], embed: Embed, min_dense_sim: float = 0.1):
        self.docs = docs
        self.embed = embed
        self.min_dense_sim = min_dense_sim
        self.bm25 = BM25(docs)  # in production: your keyword index (Elasticsearch, Postgres FTS, ...)
        self.vectors = [embed(d) for d in docs]  # in production: your vector index

    def search(self, query: str, k: int = 5, candidates: int = 20) -> list[Hit]:
        sparse = self.bm25.scores(query)
        sparse_rank = [i for i in sorted(range(len(sparse)), key=lambda i: -sparse[i]) if sparse[i] > 0][:candidates]

        qv = self.embed(query)
        sims = [_cosine(qv, v) for v in self.vectors]
        # A per-method floor keeps one retriever's junk from diluting the fusion.
        dense_rank = [
            i for i in sorted(range(len(sims)), key=lambda i: -sims[i]) if sims[i] >= self.min_dense_sim
        ][:candidates]

        fused = rrf([sparse_rank, dense_rank])
        top = sorted(fused, key=lambda i: -fused[i])[:k]
        return [
            Hit(
                i,
                self.docs[i],
                fused[i],
                sparse_rank.index(i) + 1 if i in sparse_rank else None,
                dense_rank.index(i) + 1 if i in dense_rank else None,
            )
            for i in top
        ]
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Elasticsearch / OpenSearch | BM25 plus kNN in one query; RRF built in |
| Weaviate | `hybrid` query with an alpha weighting between sparse and dense |
| Qdrant | Sparse and dense vectors on one point; fusion in the Query API |
| Vespa | Full control over ranking expressions |
| Postgres (pgvector + full-text search) | Good enough for many teams, and it's the database you already run |

## Related Patterns

- [Retrieval Quality Gate](retrieval-quality-gate.md) filters the fused candidates before they reach the prompt.
- [Retrieval Freshness Watermark](retrieval-freshness-watermark.md) adds time as a third ranking signal.
- [GraphRAG](../graph-patterns/graph-rag.md) handles relationship questions that no text retriever answers well.
- [Grounding Verifier](grounding-verifier.md) checks after generation whether retrieval was enough.

## Further Reading

- [Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf), Cormack, Clarke and Büttcher, SIGIR 2009
- [Okapi BM25](https://en.wikipedia.org/wiki/Okapi_BM25), Wikipedia. A good refresher on the scoring function.
- [Introducing Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval), Anthropic, 2024. Measures the gains from combining BM25 and embeddings, with and without reranking.
