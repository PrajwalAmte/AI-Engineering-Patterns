---
title: Retrieval Quality Gate
pillar: retrieval-and-memory
status: validated-in-production
tags: [retrieval, rag, quality-control, relevance, filtering]
related:
  - Hybrid Search
  - Context Compaction
  - Token Budget
contributors: ["@PrajwalAmte"]
last_updated: "2026-07"
description: Filter retrieved chunks by relevance before injecting into context to prevent hallucinations grounded in irrelevant content.
sidebar:
  order: 3
---

## What It Is

Retrieval Quality Gate adds a binary relevance classifier between retrieval and context assembly in RAG systems. After retrieving top-k chunks by embedding similarity, each chunk is scored for actual relevance to the query. Only chunks exceeding a relevance threshold are passed to the LLM context. Low-relevance chunks—even if they have high embedding similarity—are discarded, reducing context pollution and hallucinations grounded in tangential content.

## The Problem It Solves

Standard RAG systems retrieve by embedding similarity and blindly inject all top-k chunks into context. This fails when:

- **Ambiguous queries**: User asks "What is Python's memory model?" System retrieves chunks about Python the snake, Python the programming language, and Python web frameworks—all have high embedding similarity to "Python."
- **Noisy corpora**: Documentation wikis, logs, and heterogeneous knowledge bases contain semantically similar but off-topic content.
- **Outdated content**: Deprecated documentation has high similarity to current queries but provides incorrect guidance.
- **Tangential matches**: A chunk mentions the query keywords but doesn't help answer the question.

The result: LLMs hallucinate answers grounded in irrelevant retrieved chunks, waste token budget on noise, and produce confused responses when contradictory content enters context. Embedding similarity measures vector distance, not relevance to the information need.

## How It Works

<pre class="mermaid">
flowchart TD
    A[User query] --> B[Vector search: retrieve top-k chunks]
    B --> C[Relevance classifier scores each chunk]
    C --> D{Score > threshold?}
    D -->|Yes| E[Pass to LLM context]
    D -->|No| F[Discard chunk]
    E --> G[Assemble filtered context]
    F --> G
    G --> H{Enough chunks passed?}
    H -->|Yes| I[Generate answer with filtered context]
    H -->|No| J[Fallback: keyword search or 'insufficient context']
    I --> K[Return answer]
    J --> K
</pre>

1. **Retrieval**: Perform standard vector search or hybrid search, retrieving top-k chunks (k=10-20, larger than final context window allows)
2. **Relevance scoring**: For each retrieved chunk, score relevance to the query:
   - **Cross-encoder model**: Pass (query, chunk) pair to model trained for relevance (e.g., MS MARCO cross-encoder)
   - **LLM-as-judge**: Ask small LLM "Is this chunk relevant to answering the query?" (binary classification)
   - **Gradient-boosted classifier**: Train on (embedding_features, relevance_label) pairs from labeled data
3. **Threshold filtering**: Keep only chunks with score > threshold (e.g., 0.6 on 0-1 scale)
4. **Fallback handling**: If too few chunks pass (e.g., < 2), fall back to keyword search, expand query, or return "insufficient information" response
5. **Context assembly**: Inject filtered chunks into LLM context in relevance-score order (highest first)

The classifier must be fast (<100ms for all k chunks) and cheap to avoid negating RAG's benefits.

## When to Use It

- Open-domain question answering where queries are ambiguous
- Large, heterogeneous corpora (internal wikis, mixed documentation, logs)
- You observe hallucinations citing retrieved-but-irrelevant chunks in LLM outputs
- Context window budget is tight (4k-8k tokens) and wasted tokens hurt quality
- You have labeled relevance data or can generate it with LLM-as-judge
- Retrieval precision is low (many false positives in top-k)

## When NOT to Use It

- Small, curated corpora where retrieval precision is already >90%
- Latency budget cannot afford 50-200ms gating overhead
- You have no labeled data and cannot generate relevance judgments
- Embedding retrieval already achieves high precision (validated on test set)
- Queries are unambiguous and corpus is homogeneous (single product documentation)
- You're retrieving only k=1-3 chunks (gating overhead not justified)

## Trade-offs

1. **Latency overhead** — Relevance scoring adds 50-200ms depending on classifier complexity. Cross-encoders are accurate but slower (100-200ms for 10 chunks). Small LLMs are faster (~50ms) but less accurate. Cached embeddings + gradient-boosted trees are fastest (~10ms) but require training data.

2. **False negatives** — Chunks relevant to the query but phrased differently may be scored as irrelevant and discarded. Increases "no answer found" rate by 5-15% in practice. Requires threshold tuning and periodic review of discarded chunks.

3. **Classifier maintenance** — Cross-encoders require periodic retraining as corpus evolves. LLM-as-judge costs per-query. Gradient-boosted classifiers need labeled data and feature engineering. Adds operational complexity.

4. **Threshold calibration** — Too strict (>0.8) and most chunks are discarded; too loose (<0.4) and gating provides no benefit. Requires validation on labeled test set with precision/recall analysis.

## Failure Modes

### Overfitting to Query Phrasing
**Trigger**: Relevance classifier trained on queries with specific vocabulary. User queries use synonyms or domain jargon not in training data.  
**Symptom**: Classifier rejects chunks using "purchase" when query uses "buy," even though semantically equivalent. False negative rate spikes on out-of-vocabulary queries.  
**Mitigation**: Train classifier on paraphrased query variants. Use data augmentation (back-translation, synonym replacement). Monitor false negative rate by query type and retrain with new examples.

### Threshold Miscalibration Across Topics
**Trigger**: Threshold tuned on FAQ-style queries (high relevance expected). Applied to exploratory queries where partial relevance is useful.  
**Symptom**: Exploratory queries return "insufficient context" because no chunk scores above threshold. Users receive no answer for valid but broad questions.  
**Mitigation**: Use query-adaptive thresholds: lower threshold for broad queries (detected by query length, question type). Track "no answer" rate by query category. Allow user to request "show me everything related" mode with lower threshold.

### Classifier Brittleness to Corpus Drift
**Trigger**: Corpus adds new content types (API references after training on tutorials). Classifier trained on old content distribution.  
**Symptom**: New content scored as irrelevant despite being highly relevant. Retrieval quality degrades after corpus update.  
**Mitigation**: Retrain classifier quarterly or after major corpus updates. Use online learning or active learning to continuously update classifier. Monitor relevance scores over time and flag distribution shifts.

### Expensive Gating on High-Traffic Systems
**Trigger**: System handles 1000 QPS. Each query retrieves k=20 chunks. Classifier must score 20,000 chunk pairs per second.  
**Symptom**: Gating becomes bottleneck. Latency p99 increases from 500ms to 1500ms. GPU costs for cross-encoder exceed LLM inference costs.  
**Mitigation**: Use caching: store relevance scores for (query_embedding, chunk_id) pairs. Use approximate caching with LSH for similar queries. Batch classifier inference across concurrent requests. Switch to faster classifier (gradient-boosted trees on precomputed features).

## Implementation Example

```python
from sentence_transformers import CrossEncoder
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class Chunk:
    text: str
    chunk_id: str
    metadata: Dict
    similarity_score: float = 0.0
    relevance_score: float = 0.0

class RetrievalQualityGate:
    """
    Filters retrieved chunks by relevance before adding to LLM context.
    Uses cross-encoder model for accurate relevance scoring.
    """
    
    def __init__(
        self,
        model_name: str = 'cross-encoder/ms-marco-MiniLM-L-6-v2',
        relevance_threshold: float = 0.5,
        min_chunks: int = 2,
        max_chunks: int = 5
    ):
        """
        Args:
            model_name: HuggingFace cross-encoder model for relevance scoring
            relevance_threshold: Minimum score (0-1) to pass gate
            min_chunks: Minimum chunks to return (triggers fallback if fewer)
            max_chunks: Maximum chunks to include in context
        """
        self.model = CrossEncoder(model_name)
        self.threshold = relevance_threshold
        self.min_chunks = min_chunks
        self.max_chunks = max_chunks
    
    def score_relevance(self, query: str, chunks: List[Chunk]) -> List[Chunk]:
        """
        Score relevance of each chunk to the query.
        Returns chunks with relevance_score populated.
        """
        # Prepare (query, chunk) pairs for cross-encoder
        pairs = [(query, chunk.text) for chunk in chunks]
        
        # Batch scoring for efficiency
        scores = self.model.predict(pairs)
        
        # Attach scores to chunks
        for chunk, score in zip(chunks, scores):
            chunk.relevance_score = float(score)
        
        return chunks
    
    def filter_chunks(
        self, 
        query: str, 
        chunks: List[Chunk]
    ) -> tuple[List[Chunk], Dict]:
        """
        Filter chunks by relevance threshold.
        
        Returns:
            (filtered_chunks, metadata) tuple where metadata contains
            filtering stats for observability
        """
        # Score all chunks
        scored_chunks = self.score_relevance(query, chunks)
        
        # Filter by threshold
        passing = [
            c for c in scored_chunks 
            if c.relevance_score >= self.threshold
        ]
        
        # Sort by relevance (highest first)
        passing.sort(key=lambda c: c.relevance_score, reverse=True)
        
        # Check if we have enough chunks
        if len(passing) < self.min_chunks:
            # Fallback: return top min_chunks by relevance score
            fallback = sorted(
                scored_chunks, 
                key=lambda c: c.relevance_score, 
                reverse=True
            )[:self.min_chunks]
            
            metadata = {
                "filtered": True,
                "chunks_retrieved": len(chunks),
                "chunks_passed": len(passing),
                "chunks_returned": len(fallback),
                "fallback_triggered": True,
                "avg_relevance": sum(c.relevance_score for c in fallback) / len(fallback)
            }
            
            return fallback, metadata
        
        # Limit to max_chunks
        final = passing[:self.max_chunks]
        
        metadata = {
            "filtered": True,
            "chunks_retrieved": len(chunks),
            "chunks_passed": len(passing),
            "chunks_returned": len(final),
            "fallback_triggered": False,
            "avg_relevance": sum(c.relevance_score for c in final) / len(final),
            "min_relevance": min(c.relevance_score for c in final),
            "max_relevance": max(c.relevance_score for c in final)
        }
        
        return final, metadata


# Usage example
def rag_with_quality_gate(query: str, vector_db) -> str:
    """
    RAG pipeline with relevance-based filtering.
    """
    # 1. Retrieve top-k chunks (k larger than final context needs)
    retrieved_chunks = vector_db.similarity_search(
        query=query,
        k=15  # Retrieve more than we need
    )
    
    # Convert to Chunk objects
    chunks = [
        Chunk(
            text=doc.page_content,
            chunk_id=doc.metadata.get('id'),
            metadata=doc.metadata,
            similarity_score=doc.metadata.get('score', 0.0)
        )
        for doc in retrieved_chunks
    ]
    
    # 2. Filter by relevance
    gate = RetrievalQualityGate(
        relevance_threshold=0.6,
        min_chunks=2,
        max_chunks=5
    )
    
    filtered_chunks, filter_metadata = gate.filter_chunks(query, chunks)
    
    # 3. Check if we have sufficient context
    if filter_metadata['fallback_triggered'] and filter_metadata['avg_relevance'] < 0.4:
        return "I don't have enough relevant information to answer this question confidently."
    
    # 4. Assemble context from filtered chunks
    context = "\n\n".join([
        f"[Source {i+1}]: {chunk.text}"
        for i, chunk in enumerate(filtered_chunks)
    ])
    
    # 5. Generate answer with filtered context
    prompt = f"""Answer the question based only on the following context:

{context}

Question: {query}

Answer:"""
    
    answer = llm_call(prompt)
    
    # Log filtering stats for observability
    print(f"Retrieved: {filter_metadata['chunks_retrieved']}, "
          f"Passed: {filter_metadata['chunks_passed']}, "
          f"Used: {filter_metadata['chunks_returned']}, "
          f"Avg relevance: {filter_metadata['avg_relevance']:.2f}")
    
    return answer
```

## Tool Landscape

| Tool | Type | Notes |
|------|------|-------|
| sentence-transformers | Open-source library | Cross-encoder models for relevance scoring; MS MARCO models work well out-of-box |
| LlamaIndex | RAG framework | Supports custom node postprocessors for filtering; can integrate cross-encoders |
| LangChain | RAG framework | Contextual compression retrievers support relevance filtering with custom scorers |
| Cohere Rerank | Managed API | Production-grade reranking API; charges per-chunk scored |
| Jina Reranker | Managed API | Cross-encoder API optimized for low latency; 50ms p99 for 10 chunks |
| Elasticsearch | Search engine | Supports rescoring with custom models; can implement gating in rescore phase |
| Custom classifier | DIY | Gradient-boosted trees on embedding features; lowest latency, requires training data |

## Related Patterns

- **[Hybrid Search](hybrid-search.md)** — Hybrid search improves initial retrieval precision; quality gate further filters the hybrid results before context assembly.
- **[Context Compaction](../cost-and-efficiency/context-compaction.md)** — Context compaction summarizes chunks to fit budget; quality gate filters chunks before compaction to avoid summarizing irrelevant content.
- **[Token Budget](../cost-and-efficiency/token-budget.md)** — Token budget limits total context size; quality gate ensures budget is spent on high-relevance chunks only.
- **[Semantic Caching](../inference-and-serving/semantic-caching.md)** — Cache quality-gated contexts keyed by (query, filtered_chunk_ids) to amortize gating cost.

## Further Reading

- [Precise Zero-Shot Dense Retrieval without Relevance Labels](https://arxiv.org/abs/2212.10496) — Research on query-document relevance without fine-tuning
- [MS MARCO: A Human Generated MAchine Reading COmprehension Dataset](https://arxiv.org/abs/1611.09268) — Dataset used to train many cross-encoder models
- [Cross-Encoders for Semantic Search — Sentence-Transformers Docs](https://www.sbert.net/examples/applications/cross-encoder/README.html) — Practical guide to cross-encoder relevance models
- [When Not to Trust Your RAG System — Anthropic](https://www.anthropic.com/research) — Analysis of RAG failure modes including irrelevant retrieval
