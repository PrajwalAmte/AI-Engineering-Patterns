---
title: Embedding Drift Detector
pillar: observability-and-evaluation
status: emerging
tags: [observability, embeddings, drift, rag, monitoring]
related:
  - Span-Level Tracing
  - Hybrid Search
  - Data Contract
  - Semantic Deduplication
example: examples/observability_and_evaluation/embedding_drift_detector.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Watch two numbers on live queries, where the average query has moved and how well the index still matches them, to catch RAG degradation before users do.
sidebar:
  order: 3
---

## What It Is

A monitor over the embeddings of production queries. It tracks two numbers on a rolling window and compares them with a baseline:

- **Centroid shift:** how far the average query vector has moved. In other words, are people asking about different things than before?
- **Alignment:** the mean similarity between each query and its best-matching document. In other words, is the index still able to answer what people ask?

The first number is context. The second predicts bad answers, so it gets the tighter alert.

## The Problem It Solves

RAG fails quietly. Retrieval always returns *something*, and the model always writes fluent text from it. Consider what happens when:

- A new feature launches and users ask about webhooks, which the docs index doesn't cover yet.
- The embedding provider updates the model behind an alias, and new query vectors no longer line up with last month's document vectors.
- A content migration drops a whole section of the knowledge base.

In each case answers get worse, and the first alert you get is a user complaint. Embedding-level signals show up hours or days earlier.

## How It Works

<pre class="mermaid">
flowchart LR
    B["Baseline: queries from a known-good week<br/>→ centroid + mean best-match similarity"] --> C
    Q["Live queries"] --> W["Rolling window (e.g. last 500)"]
    W --> C{"Compare"}
    C -->|"alignment dropped > X"| A1["Alert: index can't answer<br/>what users ask"]
    C -->|"centroid moved > Y"| A2["Notice: topic mix changed"]
    C -->|"too few samples"| N["No verdict"]
</pre>

1. **Baseline.** Embed queries from a period when quality was good. Store their centroid and their mean best-match similarity against a sample of the index.
2. **Window.** Keep embeddings of recent queries. If you already embed queries for retrieval, this costs almost nothing.
3. **Compare** on a schedule. Don't produce a verdict below a minimum sample size. Small windows are noise.
4. **Route the alerts differently.** An alignment drop goes to whoever owns content and retrieval: there's a coverage gap or a model mismatch. A centroid shift with stable alignment is usually fine. Users moved, and the index kept up.

## When to Use It

- Production RAG where retrieval quality directly affects users.
- A hosted embedding model whose version you don't fully control.
- A corpus or a user base that changes month to month.

## When NOT to Use It

- **A pinned, self-hosted embedding model over a small, static corpus.** There's little that can drift, so periodic eval runs are enough.
- **You already run retrieval evals on live samples** (judged relevance of the top results). That measures the outcome directly, and this pattern is a cheaper proxy for it.

## Trade-offs

- **Proxy, not truth.** Alignment can drop because users ask harder questions that are still answerable. Confirm with a judged sample before re-indexing.
- **Baseline policy.** Re-baseline too often and you normalize real degradation. Too rarely and seasonal shifts keep paging you. Re-baseline deliberately, after confirming quality.
- **The sample of the index matters.** Comparing against a few thousand random document vectors is cheap and good enough, but refresh the sample when the corpus changes a lot.

## Failure Modes

**Seasonal false alarms.** Tax season, end of quarter, a holiday sale: the topic mix shifts every year. Compare against the same period last year, or alert only on the alignment metric during known seasonal shifts.

**Mixed embedding versions.** Half the index was re-embedded with the new model and half wasn't. Alignment drops for queries that land on the old half. Treat an embedding model change as a full re-index, and alert if two model versions are ever live at once.

**Monitoring the wrong thing.** Someone builds an elaborate per-dimension statistical test on query vectors that fires constantly and says nothing about answer quality. Start with alignment. Add other tests only if they've caught something alignment missed.

## Implementation Example

Centroid shift and query-to-index alignment over a rolling window, a minimum-sample guard, and separate alerts for each. The test simulates a launch: users start asking about webhooks, which the indexed docs don't cover, and the alignment alert fires.

```bash
cd examples && pytest observability_and_evaluation/test_embedding_drift_detector.py
```

<!-- example: examples/observability_and_evaluation/embedding_drift_detector.py -->
```python
"""Embedding Drift Detector.

Two numbers, watched over a rolling window of production queries:

1. Centroid shift: how far the average query has moved from the baseline.
   Says "users are asking about different things than before".
2. Alignment: average similarity between each query and its best document.
   Says "retrieval is finding worse matches than before". This is the one
   that predicts bad answers, so it gets the tighter alert.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

Vector = list[float]


def _cosine(a: Vector, b: Vector) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / ((sum(x * x for x in a) ** 0.5 or 1.0) * (sum(y * y for y in b) ** 0.5 or 1.0))


def _centroid(vectors: list[Vector]) -> Vector:
    n = len(vectors)
    return [sum(col) / n for col in zip(*vectors)]


@dataclass
class Baseline:
    centroid: Vector
    alignment: float  # mean best-match similarity on the baseline queries


@dataclass
class DriftReport:
    centroid_shift: float  # 1 - cos(baseline centroid, window centroid)
    alignment: float
    alignment_drop: float
    alerts: list[str] = field(default_factory=list)


@dataclass
class DriftDetector:
    embed: Callable[[str], Vector]
    index: list[Vector]  # sample of document vectors from the live index
    window: int = 500
    max_centroid_shift: float = 0.15
    max_alignment_drop: float = 0.10
    min_samples: int = 50
    baseline: Baseline | None = None
    _recent: deque = field(default_factory=deque)

    def best_match(self, q: Vector) -> float:
        return max((_cosine(q, d) for d in self.index), default=0.0)

    def fit_baseline(self, queries: list[str]) -> Baseline:
        vectors = [self.embed(q) for q in queries]
        self.baseline = Baseline(_centroid(vectors), sum(map(self.best_match, vectors)) / len(vectors))
        self._recent = deque(maxlen=self.window)
        return self.baseline

    def observe(self, query: str) -> None:
        self._recent.append(self.embed(query))

    def report(self) -> DriftReport | None:
        if self.baseline is None or len(self._recent) < self.min_samples:
            return None  # too few queries to say anything; don't alert on noise
        recent = list(self._recent)
        shift = 1 - _cosine(self.baseline.centroid, _centroid(recent))
        alignment = sum(map(self.best_match, recent)) / len(recent)
        drop = self.baseline.alignment - alignment

        alerts = []
        if drop > self.max_alignment_drop:
            alerts.append(f"retrieval alignment fell {drop:.2f} below baseline: check for gaps in the index")
        if shift > self.max_centroid_shift:
            alerts.append(f"query centroid moved {shift:.2f}: users are asking about new things")
        return DriftReport(shift, alignment, drop, alerts)
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Arize Phoenix | Embedding drift views and UMAP projections of query clusters |
| Evidently | Embedding drift tests (model-based, distance-based, share of drifted components) |
| WhyLabs / whylogs | Profiles of embedding distributions over time |
| Prometheus + your own job | Two gauges and two alerts; often enough |

## Related Patterns

- [Span-Level Tracing](span-level-tracing.md) records best-match similarity on each retrieval span, so the drift job can read it straight from traces.
- [Hybrid Search](../retrieval-and-memory/hybrid-search.md): falling dense alignment while BM25 still matches is a strong sign of an embedding model mismatch.
- [Data Contract](../data-patterns/data-contract.md) catches upstream changes before they reach the index. This pattern catches what got through.
- [Semantic Deduplication](../data-patterns/semantic-deduplication.md) should be re-run when the embedding space changes.

## Further Reading

- [Shift happens: we compared 5 methods to detect drift in ML embeddings](https://www.evidentlyai.com/blog/embedding-drift-detection), Evidently AI
- [Failing Loudly: An Empirical Study of Methods for Detecting Dataset Shift](https://arxiv.org/abs/1810.11953), Rabanser, Günnemann and Lipton, 2019
