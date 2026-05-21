---
title: Semantic Deduplication
pillar: data-patterns
status: emerging
tags: [data-quality, deduplication, embeddings, rag, indexing]
related:
  - Data Contract Pattern
  - Hybrid Search
  - Embedding Drift Detector
  - Retrieval Freshness Watermark
contributors: ["@PrajwalAmte"]
last_updated: "2026-04"
description: Deduplicate documents at the meaning level before indexing to prevent redundant chunks from wasting context window slots during retrieval.
sidebar:
  order: 2
---

## What It Is

Semantic deduplication identifies and eliminates documents (or chunks) that express the same information in different words before they enter the retrieval index. Unlike exact or near-duplicate detection (hash-based or n-gram overlap), semantic deduplication operates on meaning — catching paraphrases, reformulations, and cross-source redundancy that string-matching approaches miss entirely.

## The Problem It Solves

Real-world corpora are full of semantic duplicates that look different on the surface:

- **Cross-source redundancy**: The same product specification exists in a marketing page, a support FAQ, a technical datasheet, and an internal wiki. Each is worded differently. All four get indexed. When a user asks about the product, the retriever returns 3-4 chunks that say the same thing, wasting context window slots that could have held diverse, useful information.
- **Version accumulation**: Documentation evolves through revisions. Old and new versions coexist in the index. A query about "authentication setup" retrieves chunks from v1.0, v1.2, and v2.0 — mostly redundant, occasionally contradictory.
- **Template-generated content**: Automated systems produce content from templates (release notes, incident reports, onboarding guides). Hundreds of near-identical documents differ only in entity names or dates, inflating the index without adding unique knowledge.
- **Summarization echoes**: Content pipelines that generate summaries create derivative documents that overlap heavily with their sources. Both the source and summary get indexed.

The downstream impact is measurable: studies show that 20-40% redundancy in RAG indices leads to 15-25% retrieval recall degradation because redundant chunks displace diverse, relevant results.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Raw documents/chunks"] --> B["Generate embeddings"]
    B --> C["Build similarity graph (ANN)"]
    C --> D["Cluster chunks above similarity threshold"]
    D --> E["Select canonical chunk per cluster"]
    E --> F{"Canonical selection strategy"}
    F -->|"Most recent"| G["Pick freshest document"]
    F -->|"Most complete"| H["Pick longest/most detailed"]
    F -->|"Highest authority"| I["Pick from preferred source"]
    G --> J["Index only canonical chunks"]
    H --> J
    I --> J
    J --> K["Store dedup mapping for provenance"]
</pre>

1. **Embedding computation**: Generate embeddings for all documents or chunks using the same embedding model as the retrieval index.
2. **Similarity graph**: Build a pairwise similarity graph using approximate nearest neighbor (ANN) search. Connect any two chunks whose cosine similarity exceeds the deduplication threshold (typically 0.92-0.97).
3. **Cluster formation**: Identify connected components or apply clustering (agglomerative, DBSCAN) on the similarity graph. Each cluster represents a set of semantically equivalent chunks.
4. **Canonical selection**: From each cluster, select one canonical chunk using a configurable strategy — most recent, most complete (longest or most detailed), from the most authoritative source, or a combination.
5. **Index canonical only**: Index the canonical chunks. Store the deduplication mapping (which chunks were merged, which was selected as canonical) for provenance and debugging.
6. **Incremental dedup**: When new documents arrive, embed them and check against existing clusters before indexing. Add to an existing cluster or create a new one.

## When to Use It

- Your corpus is assembled from multiple sources that cover overlapping topics (documentation sites, support databases, wikis, knowledge bases).
- You have observed retrieval results returning redundant chunks that say the same thing in different words.
- Your context window is constrained and every slot matters — wasting 3 of 5 slots on redundant content noticeably degrades answer quality.
- The corpus grows over time with version accumulation or template-generated content.

## When not to Use It

- Your corpus is curated and each document is unique by construction (a single-source, well-maintained documentation site). Deduplication adds processing cost without removing meaningful duplicates.
- Subtle differences between similar documents are important. Legal documents, contract variations, or regulatory texts may look semantically identical but differ in critical details (dates, amounts, clauses). Deduplication could discard legally distinct documents.
- Your retrieval pipeline already handles redundancy at query time (e.g., MMR — Maximal Marginal Relevance — diversifies results). If retrieval-time dedup is sufficient, index-time dedup is redundant effort.
- The corpus is small enough that redundancy is not a practical problem (fewer than 1,000 chunks).

## Trade-offs

1. **Threshold sensitivity** — Too aggressive (low threshold): merge chunks that are related but not equivalent, losing distinct information. Too conservative (high threshold): miss genuine duplicates. Requires per-corpus calibration.
2. **Canonical selection risk** — The canonical chunk may not always be the best version for every query. A summary might be canonical, but a specific query needs the detailed original. Store the dedup mapping to allow fallback retrieval from non-canonical chunks when needed.
3. **Processing cost** — Computing pairwise similarity across a large corpus is expensive. ANN indices reduce this from O(n^2) to approximately O(n log n), but for millions of chunks, the indexing pipeline adds meaningful compute time.
4. **Incremental consistency** — As new documents arrive, they must be checked against all existing clusters. Over time, cluster boundaries can drift. Periodic full re-deduplication may be necessary.

## Failure Modes

### False Merge of Legally Distinct Documents
**Trigger**: Two documents are semantically similar but differ in critical details (dates, amounts, version numbers, jurisdiction-specific terms).
**Symptom**: The canonical chunk omits the critical distinction. Retrieval serves the canonical version, and the LLM produces answers that are wrong for the user's specific context.
**Mitigation**: Before merging, compare named entities and numerical values between candidate duplicates. If structured data differs, keep both chunks as separate entries even if embedding similarity is high.

### Cluster Drift Over Time
**Trigger**: Incremental deduplication adds new chunks to existing clusters, and the cluster centroid gradually shifts away from the original canonical meaning.
**Symptom**: Clusters start absorbing tangentially related content. The canonical chunk no longer represents the cluster well. Retrieval quality degrades as clusters become incoherent.
**Mitigation**: Periodically re-compute cluster centroids and validate that the canonical chunk is still the closest member to the centroid. Schedule full re-deduplication quarterly or when cluster quality metrics drop.

### Embedding Model Mismatch
**Trigger**: The embedding model used for deduplication differs from the one used for retrieval, or the dedup model is updated without re-running deduplication.
**Symptom**: Chunks that are duplicates under one model's embedding space are not duplicates under the other's. Either the index contains duplicates (dedup missed them) or distinct chunks were incorrectly merged.
**Mitigation**: Use the same embedding model for deduplication and retrieval. When the embedding model is updated, re-run deduplication before rebuilding the retrieval index.

## Implementation Example

```python
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Chunk:
    chunk_id: str
    content: str
    source: str
    created_at: float
    embedding: np.ndarray | None = None


@dataclass
class DedupCluster:
    canonical_id: str
    member_ids: list[str]
    similarity_scores: list[float]


class SemanticDeduplicator:
    def __init__(
        self,
        similarity_threshold: float = 0.95,
        canonical_strategy: str = "most_recent",
    ):
        self._threshold = similarity_threshold
        self._strategy = canonical_strategy
        self._chunks: dict[str, Chunk] = {}
        self._clusters: list[DedupCluster] = []

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        dot = np.dot(a, b)
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        if norm == 0:
            return 0.0
        return float(dot / norm)

    def _find_similar(self, embedding: np.ndarray) -> list[tuple[str, float]]:
        matches = []
        for cid, chunk in self._chunks.items():
            if chunk.embedding is not None:
                sim = self._cosine_similarity(embedding, chunk.embedding)
                if sim >= self._threshold:
                    matches.append((cid, sim))
        return matches

    def _select_canonical(self, chunk_ids: list[str]) -> str:
        chunks = [self._chunks[cid] for cid in chunk_ids if cid in self._chunks]
        if not chunks:
            return chunk_ids[0]

        if self._strategy == "most_recent":
            return max(chunks, key=lambda c: c.created_at).chunk_id
        elif self._strategy == "most_complete":
            return max(chunks, key=lambda c: len(c.content)).chunk_id
        else:
            return chunks[0].chunk_id

    def add_chunk(self, chunk: Chunk) -> tuple[bool, str]:
        self._chunks[chunk.chunk_id] = chunk

        if chunk.embedding is None:
            return True, chunk.chunk_id

        similar = self._find_similar(chunk.embedding)

        if not similar:
            self._clusters.append(
                DedupCluster(
                    canonical_id=chunk.chunk_id,
                    member_ids=[chunk.chunk_id],
                    similarity_scores=[1.0],
                )
            )
            return True, chunk.chunk_id

        for cluster in self._clusters:
            cluster_member_sims = [
                (mid, sim) for mid, sim in similar if mid in cluster.member_ids
            ]
            if cluster_member_sims:
                cluster.member_ids.append(chunk.chunk_id)
                cluster.similarity_scores.append(
                    max(sim for _, sim in cluster_member_sims)
                )
                cluster.canonical_id = self._select_canonical(cluster.member_ids)
                return False, cluster.canonical_id

        self._clusters.append(
            DedupCluster(
                canonical_id=chunk.chunk_id,
                member_ids=[chunk.chunk_id],
                similarity_scores=[1.0],
            )
        )
        return True, chunk.chunk_id

    def get_canonical_chunks(self) -> list[Chunk]:
        canonical_ids = {c.canonical_id for c in self._clusters}
        return [self._chunks[cid] for cid in canonical_ids if cid in self._chunks]

    def get_dedup_report(self) -> dict:
        total_chunks = sum(len(c.member_ids) for c in self._clusters)
        canonical_count = len(self._clusters)
        duplicates_removed = total_chunks - canonical_count
        return {
            "total_chunks_processed": total_chunks,
            "canonical_chunks": canonical_count,
            "duplicates_removed": duplicates_removed,
            "dedup_ratio": duplicates_removed / max(total_chunks, 1),
            "clusters": len(self._clusters),
        }
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| MinHash + LSH (datasketch) | Open-source library | Fast approximate dedup using locality-sensitive hashing; catches near-duplicates, not semantic |
| Qdrant + clustering | Vector database | Use Qdrant's search to find similar chunks, then cluster externally |
| Pinecone + dedup pipeline | Managed vector DB | Query-before-insert pattern with similarity threshold |
| Cleanlab | Open-source library | Identifies near-duplicate and outlier data points using embeddings |
| Custom pipeline | DIY | Most control over canonical selection strategy and cluster management |

## Related Patterns

- **[Data Contract Pattern](/AI-Engineering-Patterns/patterns/data-patterns/data-contract/)** — Data contracts can mandate deduplication as a quality requirement before data enters the index.
- **[Hybrid Search](/AI-Engineering-Patterns/patterns/retrieval-and-memory/hybrid-search/)** — Deduplicated indices improve hybrid search precision by removing redundant BM25 and vector matches.
- **[Embedding Drift Detector](/AI-Engineering-Patterns/patterns/observability/embedding-drift-detector/)** — Deduplication should be re-run when embedding drift is detected, as similarity thresholds may need recalibration.
- **[Retrieval Freshness Watermark](/AI-Engineering-Patterns/patterns/retrieval-and-memory/retrieval-freshness-watermark/)** — Freshness metadata informs the canonical selection strategy: prefer the most recent version.

## Further Reading

- [SemDeDup: Data-efficient Learning at Web-Scale through Semantic Deduplication (Abbas et al., 2023)](https://arxiv.org/abs/2303.09540)
- [D4: Improving LLM Pretraining via Document De-Duplication and Diversification](https://arxiv.org/abs/2308.12284)
- [Deduplication and the Quality of Training Data for Large Language Models — Google Research](https://blog.research.google/2022/08/deduplication-and-quality-of-training-data.html)
