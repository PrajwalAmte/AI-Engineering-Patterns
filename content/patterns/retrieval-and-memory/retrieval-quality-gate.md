---
title: Retrieval Quality Gate
pillar: retrieval-and-memory
status: emerging
tags: [retrieval, rag, reranking, relevance, abstention]
related:
  - Hybrid Search
  - Grounding Verifier
  - Context Compaction
  - Token Budget
example: examples/retrieval_and_memory/retrieval_quality_gate.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Score retrieved chunks for relevance to this query, drop the ones that don't help, and abstain when nothing does.
sidebar:
  order: 3
---

## What It Is

A filter between retrieval and the prompt. Each retrieved chunk is scored for whether it helps answer *this* question, usually by a reranker or cross-encoder. Chunks below a threshold, or far below the best chunk, are dropped. If nothing useful is left, the system says it doesn't know instead of asking the model to answer from noise.

Rerankers are widely used. The emerging part is treating the reranker's score as a *gate* with an abstain path, not just a sort order.

## The Problem It Solves

Vector search always returns k results, however bad the best match is. Ask a support bot about parental leave when the knowledge base has no leave policy, and it will still get five chunks: perhaps a holiday calendar, a benefits FAQ and an office address. The model then does what it's told and answers from those, producing something plausible and wrong.

Ambiguity causes the same problem. "Python memory model" pulls in chunks about the language, the style guide and, in a broad enough corpus, the snake. Each irrelevant chunk takes up tokens and gives the model something to get confused by.

## How It Works

<pre class="mermaid">
flowchart TD
    Q["Query"] --> R["Retrieve top 20–50<br/>(hybrid search)"]
    R --> S["Score each (query, chunk)<br/>with a reranker"]
    S --> F["Keep if score ≥ threshold<br/>AND ≥ ratio × best score"]
    F --> E{"Anything kept?"}
    E -->|"yes"| P["Prompt with kept chunks,<br/>best first"]
    E -->|"no"| A["Abstain: 'not in the knowledge base'"]
    F -.->|"log dropped chunks + scores"| L["Review for false negatives"]
</pre>

1. **Over-retrieve.** Pull more candidates than you'll use. The gate is the precision step, so retrieval can aim for recall.
2. **Score each pair.** A cross-encoder or a reranker API (Cohere, Voyage, Jina, or an open model) reads the query and the chunk together. That's much more precise than comparing two independently computed embeddings.
3. **Apply two cutoffs.** An absolute threshold ("is this relevant at all?") and a relative one ("is it close to the best chunk?"). The relative cutoff drops the tail of weak matches when one chunk is clearly the answer.
4. **Abstain when nothing survives.** A clear "I couldn't find this" is better than a confident invention, and users trust the product more for it.
5. **Log what was dropped.** Reviewing a sample of dropped chunks is how you find out the threshold is too strict.

## When to Use It

- The knowledge base doesn't cover everything users will ask, which is true of every knowledge base.
- The corpus is large and mixed (wikis, tickets, docs from several products), so near-misses are common.
- You've seen answers built from retrieved but irrelevant chunks.

## When NOT to Use It

- **A small, curated corpus where retrieval is already precise.** Measure precision@k first. If it's high, the gate adds latency for nothing.
- **Exploratory search UIs** where the user *wants* loosely related results to browse.
- **You only retrieve one to three chunks** from a narrow index. There's little to filter.

## Trade-offs

- **Latency and cost.** A cross-encoder over 20–50 candidates adds tens to hundreds of milliseconds. Hosted rerankers charge per document scored.
- **False negatives become "I don't know".** A strict gate turns some answerable questions into abstentions. Track the abstention rate next to answer quality. Abstentions that a human could answer are your false negatives.
- **Thresholds don't transfer.** Rerankers' scores are calibrated differently, and a new model version can shift them. Re-tune when you change the model.

## Failure Modes

**Abstaining on broad questions.** "Tell me about our security practices" has no single highly relevant chunk, only many moderately relevant ones. A threshold tuned on FAQ questions rejects all of them. Lower the absolute threshold for broad queries, or rely on the relative cutoff alone.

**Synonym blindness.** A scorer that leans on word overlap, like the toy one in the example, rejects "purchase" when the user wrote "buy". Use a real cross-encoder in production. The lexical scorer is only there so the tests run offline.

**The gate becomes the bottleneck.** At high QPS, scoring 50 candidates per query costs more GPU than generation does. Score fewer candidates, batch across requests, or cache scores for popular (query, chunk) pairs.

## Implementation Example

Absolute and relative cutoffs, an abstain path that never calls the model, and the dropped list kept for review. Replace `lexical_score` with your reranker. The rest stays the same.

```bash
cd examples && pytest retrieval_and_memory/test_retrieval_quality_gate.py
```

<!-- example: examples/retrieval_and_memory/retrieval_quality_gate.py -->
```python
"""Retrieval Quality Gate.

Score every retrieved chunk for whether it helps answer *this* query, drop
the ones that don't, and if too little survives, say so instead of letting the
model improvise from noise.

`score(query, chunk) -> float in [0, 1]` is the pluggable part: a
cross-encoder or reranker API in production, a cheap lexical scorer here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

Scorer = Callable[[str, str], float]

_STOP = set("a an the is are was what how do does to of in on for and or my i it".split())


def lexical_score(query: str, chunk: str) -> float:
    q = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in _STOP}
    c = set(re.findall(r"[a-z0-9]+", chunk.lower()))
    return len(q & c) / len(q) if q else 0.0


@dataclass
class GateResult:
    decision: str  # "answer" | "abstain"
    kept: list[tuple[str, float]] = field(default_factory=list)
    dropped: list[tuple[str, float]] = field(default_factory=list)


def gate(
    query: str,
    chunks: list[str],
    score: Scorer = lexical_score,
    threshold: float = 0.5,
    relative_cutoff: float = 0.6,  # also drop anything far below the best chunk
    min_kept: int = 1,
    max_kept: int = 5,
) -> GateResult:
    scored = sorted(((c, score(query, c)) for c in chunks), key=lambda p: -p[1])
    best = scored[0][1] if scored else 0.0
    floor = max(threshold, best * relative_cutoff)

    kept = [p for p in scored if p[1] >= floor][:max_kept]
    dropped = [p for p in scored if p not in kept]
    # Log `dropped` with its scores: reviewing what the gate threw away is how
    # you find a threshold that's too strict.
    return GateResult("answer" if len(kept) >= min_kept else "abstain", kept, dropped)


def answer(query: str, chunks: list[str], llm: Callable[[str], str], **gate_kwargs) -> str:
    result = gate(query, chunks, **gate_kwargs)
    if result.decision == "abstain":
        return "I couldn't find anything in the knowledge base that answers that."
    context = "\n\n".join(c for c, _ in result.kept)
    return llm(f"Answer using only this context:\n{context}\n\nQuestion: {query}")
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Cohere Rerank, Voyage rerank, Jina Reranker | Hosted rerankers; return a relevance score per document |
| sentence-transformers CrossEncoder | Open models (e.g. MS MARCO MiniLM, BGE reranker) you can self-host |
| LlamaIndex, LangChain | Node postprocessors and compression retrievers with similarity cutoffs |

## Related Patterns

- [Hybrid Search](hybrid-search.md) is the high-recall retriever the gate should sit behind.
- [Grounding Verifier](grounding-verifier.md) checks the answer after generation. The gate checks the inputs before it.
- [Context Compaction](../cost-and-efficiency/context-compaction.md): gate first, then compact. There's no point summarizing irrelevant chunks.
- [Token Budget](../cost-and-efficiency/token-budget.md): the gate makes sure the budget is spent on chunks that help.

## Further Reading

- [Corrective Retrieval Augmented Generation (CRAG)](https://arxiv.org/abs/2401.15884), Yan et al., 2024. Grades retrieved documents and takes corrective action on low confidence.
- [Retrieve & Re-Rank](https://www.sbert.net/examples/applications/retrieve_rerank/README.html), sentence-transformers documentation
- [MS MARCO: A Human Generated MAchine Reading COmprehension Dataset](https://arxiv.org/abs/1611.09268). Most open cross-encoders are trained on it.
