---
title: Hybrid Search
pillar: retrieval-and-memory
status: validated-in-production
tags: [retrieval, rag, search, embeddings, bm25]
related:
  - Classic RAG Pattern
  - Reranking Pattern
  - Chunking Strategy Pattern
  - GraphRAG Pattern
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Combine dense vector search with sparse BM25 keyword search for retrieval that consistently outperforms either method alone.
sidebar:
  order: 3
---

## What It Is

Hybrid search combines two fundamentally different retrieval approaches — dense vector search (semantic similarity) and sparse keyword search (lexical matching like BM25) — then merges their results using a fusion algorithm. This captures both semantic meaning and exact keyword matches, consistently outperforming either method used alone.

## The Problem It Solves

Dense retrieval (embeddings) captures meaning but misses exact terms. A query for "error code E-4012" will not match a document about that error code if the embedding space was not trained on that specific identifier. Sparse retrieval (BM25) captures exact terms but misses semantics. "How to fix authentication issues" will not match a document titled "Resolving login failures."

Using either approach alone leaves a class of queries poorly served:

- **Dense only**: Misses exact identifiers, product names, error codes, and specialized terminology.
- **Sparse only**: Misses paraphrases, synonyms, and conceptual similarity.

Hybrid search addresses both weaknesses by retrieving candidates from both systems and fusing the results.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Query"] --> B["Dense retrieval (embeddings)"]
    A --> C["Sparse retrieval (BM25)"]
    B --> D["Top-K dense results"]
    C --> E["Top-K sparse results"]
    D --> F["Reciprocal Rank Fusion (RRF)"]
    E --> F
    F --> G["Optional reranking"]
    G --> H["Merged top-K results"]
</pre>

1. The query is sent to both retrieval systems in parallel.
2. Dense retrieval embeds the query and performs approximate nearest neighbor search against the document embeddings.
3. Sparse retrieval runs BM25 (or similar) against the keyword index.
4. Results from both systems are merged using a fusion algorithm. The most common approach is **Reciprocal Rank Fusion (RRF)**, which combines rankings without requiring score normalization.
5. The fused top-K results are returned, optionally followed by a reranking step.

**Reciprocal Rank Fusion formula:**

$$\text{RRF}(d) = \sum_{r \in R} \frac{1}{k + \text{rank}_r(d)}$$

Where $R$ is the set of result lists, $\text{rank}_r(d)$ is the rank of document $d$ in list $r$, and $k$ is a constant (typically 60) that controls how much weight is given to top-ranked results.

## When to Use It

- Your document corpus contains both natural language content and structured identifiers (codes, product names, technical terms).
- You need robust retrieval across diverse query types — from keyword lookups to conceptual questions.
- You are building a RAG system and want the highest baseline retrieval quality before investing in more complex approaches.
- Your evaluation shows that neither dense nor sparse retrieval alone achieves acceptable recall.

## When not to Use It

- Your queries and documents are pure natural language with no specialized terminology. Dense retrieval alone may be sufficient, and the added complexity of hybrid search provides marginal improvement.
- Your corpus is extremely small (under 1,000 documents). At small scale, the difference between retrieval methods is negligible, and a simple embedding search is adequate.
- You cannot operationally maintain two search indices. Hybrid search requires both a vector store and a keyword index, doubling indexing infrastructure.
- Latency constraints are extremely tight. Running two searches in parallel and fusing results adds overhead compared to a single retrieval path.

## Trade-offs

1. **Infrastructure complexity** — Two search systems to maintain, index, and keep in sync. Any document update must be reflected in both indices.
2. **Tuning the fusion** — The relative weight of dense vs. sparse results affects quality. The optimal ratio varies by domain and query distribution. RRF is a good default but may not be optimal.
3. **Increased indexing cost** — Documents must be both embedded (compute-intensive) and tokenized for BM25 (I/O-intensive). Indexing takes longer and uses more storage.
4. **Diminishing returns with reranking** — If you add a reranking step after hybrid search, the reranker often compensates for weaknesses in individual retrieval methods, reducing the marginal benefit of hybrid over dense-only + reranker.

## Failure Modes

### Index Synchronization Lag
**Trigger**: Document updates are applied to the vector store but the keyword index (or vice versa) lags behind due to different indexing pipelines.
**Symptom**: Hybrid results become inconsistent — a query returns a document from one index that is missing or outdated in the other. Fusion scores are skewed because one result list is stale.
**Mitigation**: Use a single ingestion pipeline that writes to both indices atomically. If that is not possible, add a freshness check that flags results where the two indices disagree on document version.

### Fusion Weight Mismatch
**Trigger**: The dense-vs-sparse weight ratio was tuned on one query distribution, but traffic shifts (new user segment, new content type).
**Symptom**: Retrieval quality drops for one class of queries. Keyword-heavy queries underperform if dense weight dominates, or vice versa. The drop is hard to detect because overall metrics average out.
**Mitigation**: Monitor recall per query type, not just aggregate. Consider query-adaptive fusion weights — use a lightweight classifier to adjust the ratio based on query characteristics (length, presence of jargon).

### Embedding-Keyword Disagreement on Ambiguous Queries
**Trigger**: A query like "Python" matches programming documentation via embeddings but snake-related content via keyword.
**Symptom**: Fusion surfaces irrelevant results from the weaker method that dilute the top-k context window.
**Mitigation**: Apply a minimum relevance threshold per method before fusion. Results below the threshold from either method are excluded from the merge.

## Implementation Example

```python
from dataclasses import dataclass
import math


@dataclass
class SearchResult:
    doc_id: str
    content: str
    score: float


def bm25_search(query: str, corpus: dict[str, str], k: int = 10) -> list[SearchResult]:
    query_terms = query.lower().split()
    scores: dict[str, float] = {}
    n = len(corpus)
    avg_dl = sum(len(doc.split()) for doc in corpus.values()) / max(n, 1)

    df: dict[str, int] = {}
    for doc in corpus.values():
        seen = set(doc.lower().split())
        for term in seen:
            df[term] = df.get(term, 0) + 1

    k1, b = 1.5, 0.75

    for doc_id, doc in corpus.items():
        doc_terms = doc.lower().split()
        dl = len(doc_terms)
        tf: dict[str, int] = {}
        for t in doc_terms:
            tf[t] = tf.get(t, 0) + 1

        score = 0.0
        for term in query_terms:
            if term not in tf:
                continue
            term_df = df.get(term, 0)
            idf = math.log((n - term_df + 0.5) / (term_df + 0.5) + 1)
            term_tf = tf[term]
            numerator = term_tf * (k1 + 1)
            denominator = term_tf + k1 * (1 - b + b * dl / avg_dl)
            score += idf * numerator / denominator

        if score > 0:
            scores[doc_id] = score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
    return [SearchResult(doc_id=d, content=corpus[d], score=s) for d, s in ranked]


def dense_search(
    query_embedding: list[float],
    doc_embeddings: dict[str, list[float]],
    corpus: dict[str, str],
    k: int = 10,
) -> list[SearchResult]:
    import numpy as np

    q = np.array(query_embedding)
    scores = {}
    for doc_id, emb in doc_embeddings.items():
        d = np.array(emb)
        cos_sim = float(np.dot(q, d) / (np.linalg.norm(q) * np.linalg.norm(d) + 1e-10))
        scores[doc_id] = cos_sim

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
    return [SearchResult(doc_id=d, content=corpus[d], score=s) for d, s in ranked]


def reciprocal_rank_fusion(
    *result_lists: list[SearchResult],
    k: int = 60,
    top_n: int = 10,
) -> list[SearchResult]:
    rrf_scores: dict[str, float] = {}
    content_map: dict[str, str] = {}

    for results in result_lists:
        for rank, result in enumerate(results):
            rrf_scores[result.doc_id] = rrf_scores.get(result.doc_id, 0.0) + (
                1.0 / (k + rank + 1)
            )
            content_map[result.doc_id] = result.content

    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [
        SearchResult(doc_id=d, content=content_map[d], score=s)
        for d, s in ranked
    ]


def hybrid_search(
    query: str,
    query_embedding: list[float],
    corpus: dict[str, str],
    doc_embeddings: dict[str, list[float]],
    k: int = 10,
) -> list[SearchResult]:
    sparse_results = bm25_search(query, corpus, k=k)
    dense_results = dense_search(query_embedding, doc_embeddings, corpus, k=k)
    return reciprocal_rank_fusion(sparse_results, dense_results, top_n=k)
```

For production systems, use a database that natively supports hybrid search (Weaviate, Qdrant, Elasticsearch with vector search) instead of running separate systems.

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| Weaviate | Vector database | Native hybrid search with configurable dense/sparse weighting |
| Qdrant | Vector database | Supports sparse vectors alongside dense, enabling hybrid retrieval |
| Elasticsearch | Search engine | kNN vector search + BM25 in a single query |
| Pinecone | Managed vector DB | Sparse-dense hybrid search with integrated dot-product fusion |
| LanceDB | Embedded vector DB | Full-text search + vector search with reranking support |

## Related Patterns

- **[Classic RAG Pattern](/AI-Engineering-Patterns/patterns/retrieval-and-memory/classic-rag/)** — Hybrid search is an upgrade to the retrieval component in classic RAG.
- **[Reranking Pattern](/AI-Engineering-Patterns/patterns/retrieval-and-memory/reranking/)** — Typically applied after hybrid search for further precision improvement.
- **[Chunking Strategy Pattern](/AI-Engineering-Patterns/patterns/retrieval-and-memory/chunking-strategy/)** — Chunk size affects both dense and sparse retrieval quality.
- **[GraphRAG Pattern](/AI-Engineering-Patterns/patterns/graph-patterns/graph-rag/)** — For relational queries where neither hybrid nor dense search is sufficient.

## Further Reading

- [Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods (Cormack et al.)](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- [Hybrid Search Explained — Weaviate Documentation](https://weaviate.io/blog/hybrid-search-explained)
- [BM25 — The Probabilistic Relevance Framework](https://en.wikipedia.org/wiki/Okapi_BM25)
