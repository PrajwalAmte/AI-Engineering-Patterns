---
title: Entity Resolution Graph
pillar: graph-patterns
status: emerging
tags: [entity-resolution, deduplication, knowledge-graph, data-quality]
related:
  - GraphRAG
  - Semantic Deduplication
  - Data Contract
example: examples/graph_patterns/entity_resolution_graph.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Decide which records across sources are the same entity using a match graph, and never let one fuzzy link chain two different entities together.
sidebar:
  order: 2
---

## What It Is

Records from different systems ("Acme Inc." in the CRM, "ACME Incorporated" in billing, "Acme" in support tickets) become nodes in a graph. Pairs that probably refer to the same real-world entity get an edge with a score. Clusters of connected records become one canonical entity.

Entity resolution (record linkage) is decades old. What makes it a pattern for AI systems is where it sits: in front of knowledge graphs and RAG indexes, where duplicate entities silently break multi-hop answers. The safeguard this page stresses is *conflict-aware* clustering.

## The Problem It Solves

Without resolution, your knowledge graph holds three Acmes. Facts about Acme's contract are on one node and facts about its support tickets on another, so "does Acme have open P1s on an expiring contract?" can't be answered by traversal. The answer exists, split across three nodes.

Naive resolution fails the other way. Plain connected components over fuzzy matches can chain "Apex Labs" to "Apex" to "Apex Dental", and two unrelated companies become one entity. The model then reports one company's outage to the other's account manager.

## How It Works

<pre class="mermaid">
flowchart LR
    R["Records from all sources"] --> N["Normalize names<br/>(case, punctuation, Inc/LLC/GmbH)"]
    N --> B["Blocking: only compare<br/>records sharing a name token"]
    B --> S["Score pairs: name overlap<br/>+ agreeing attributes"]
    S --> M["Merge strongest edges first"]
    M --> C{"Merge would join records<br/>with conflicting IDs?"}
    C -->|"yes"| X["Reject; log for review"]
    C -->|"no"| U["Union clusters"]
    U --> E["Canonical entities + match edges"]
</pre>

1. **Normalize** names: lowercase, strip punctuation, remove legal suffixes, expand "&".
2. **Block** to avoid comparing every pair: only records sharing a meaningful token (or an LSH bucket) are candidates.
3. **Score** pairs from name similarity plus agreeing attributes (email domain, city). A matching strong identifier such as a tax ID is decisive.
4. **Merge in order of strength,** and refuse any merge that would put two records with *different* strong identifiers in the same cluster. This one rule prevents chaining.
5. **Keep the edges and the rejections.** Edges explain why records were merged. Rejections are the review queue.

## When to Use It

- You're building a knowledge graph or entity-centric RAG from more than one source.
- The same people, companies or products appear under different names and IDs.
- Wrong merges are costly: customer data, compliance, financial reporting.

## When NOT to Use It

- **A shared ID already exists.** If every system carries the same customer ID, join on it.
- **One clean source.** Resolution solves cross-source mess. Within one well-run system it's mostly unnecessary.

## Trade-offs

- **Precision against recall.** A lower threshold merges more true duplicates and more false ones. False merges usually hurt more, so lean conservative and send uncertain pairs to review.
- **Blocking misses pairs.** Records with no shared token ("IBM" and "International Business Machines") are never compared. Add alias tables or embedding-based blocking for known abbreviations.
- **Clusters need maintenance.** New records arrive daily. Incremental resolution is cheaper, but periodic full re-runs catch drift.

## Failure Modes

**Transitive chaining.** A vague record ("Apex", no other attributes) bridges two distinct entities. Conflict-aware merging blocks it, and the example tests exactly this case.

**Over-trusting the LLM as matcher.** LLM pairwise judgments are good at hard cases ("is 'Big Blue' IBM?") and expensive at scale, and they're inconsistent on borderline pairs. Use rules and scores for most pairs and the LLM for the uncertain middle band.

**No review loop.** Rejected merges and low-confidence edges pile up unread. Someone must own the queue, or the conservative threshold quietly becomes a recall problem.

## Implementation Example

Normalization, token blocking, attribute-aware scoring, strongest-first merging with a conflict check on strong identifiers, and a log of rejected merges. The tests include the chaining case and a same-name, different-tax-ID pair.

```bash
cd examples && pytest graph_patterns/test_entity_resolution_graph.py
```

<!-- example: examples/graph_patterns/entity_resolution_graph.py -->
```python
"""Entity Resolution Graph.

Decide which records from different sources are the same real-world entity.
Records are nodes; an edge means "probably the same". Clusters are connected
components, with one safeguard that plain connected components lacks: a
cluster is never allowed to contain two records with *conflicting* strong
identifiers (different emails, different tax IDs). That stops one fuzzy edge
from chaining two different companies together.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

SUFFIXES = re.compile(r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|gmbh|plc)\b\.?", re.I)


@dataclass
class Record:
    id: str
    source: str
    name: str
    email_domain: str | None = None
    tax_id: str | None = None
    city: str | None = None


def normalize(name: str) -> str:
    name = SUFFIXES.sub("", name.lower().replace("&", " and "))
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", name)).strip()


def tokens(name: str) -> set[str]:
    return set(normalize(name).split())


def score(a: Record, b: Record) -> float:
    """0-1 match score from name overlap plus agreeing attributes."""
    ta, tb = tokens(a.name), tokens(b.name)
    name = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    bonus = 0.0
    if a.email_domain and a.email_domain == b.email_domain:
        bonus += 0.4
    if a.city and a.city == b.city:
        bonus += 0.1
    if a.tax_id and a.tax_id == b.tax_id:
        return 1.0
    return min(1.0, name * 0.7 + bonus)


def _conflict(a: Record, b: Record) -> bool:
    return bool(
        (a.tax_id and b.tax_id and a.tax_id != b.tax_id)
        or (a.email_domain and b.email_domain and a.email_domain != b.email_domain)
    )


def blocks(records: list[Record]) -> dict[str, list[Record]]:
    """Only compare records sharing a name token, so cost isn't O(n²) over everything."""
    out: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        for t in tokens(r.name):
            if len(t) > 2:
                out[t].append(r)
    return out


@dataclass
class Resolution:
    clusters: list[list[Record]]
    edges: list[tuple[str, str, float]] = field(default_factory=list)
    rejected: list[tuple[str, str, str]] = field(default_factory=list)  # merges blocked by conflicts


def resolve(records: list[Record], threshold: float = 0.6) -> Resolution:
    by_id = {r.id: r for r in records}
    candidate_pairs = set()
    for group in blocks(records).values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                candidate_pairs.add(tuple(sorted((a.id, b.id))))

    scored = sorted(
        ((score(by_id[a], by_id[b]), a, b) for a, b in candidate_pairs), reverse=True
    )  # strongest evidence merges first
    cluster_of = {r.id: {r.id} for r in records}
    result = Resolution([])
    for s, a, b in scored:
        if s < threshold or cluster_of[a] is cluster_of[b]:
            continue
        ca, cb = cluster_of[a], cluster_of[b]
        clash = next(((x, y) for x in ca for y in cb if _conflict(by_id[x], by_id[y])), None)
        if clash:
            result.rejected.append((a, b, f"conflicting identifiers between {clash[0]} and {clash[1]}"))
            continue
        merged = ca | cb
        for rid in merged:
            cluster_of[rid] = merged
        result.edges.append((a, b, round(s, 2)))

    unique = {id(c): c for c in cluster_of.values()}.values()
    result.clusters = [sorted((by_id[i] for i in c), key=lambda r: r.id) for c in unique]
    return result
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Splink | Probabilistic record linkage (Fellegi–Sunter) at scale on Spark/DuckDB |
| dedupe | Active-learning entity resolution in Python |
| Zingg | Open-source ML entity resolution on Spark |
| Senzing | Commercial entity resolution engine |

## Related Patterns

- [GraphRAG](graph-rag.md) depends on resolved entities for traversal to work.
- [Semantic Deduplication](../data-patterns/semantic-deduplication.md) deduplicates *documents*. This pattern deduplicates *entities*.
- [Data Contract](../data-patterns/data-contract.md) can require sources to provide the strong identifiers that make resolution reliable.

## Further Reading

- [Splink documentation](https://moj-analytical-services.github.io/splink/)
- [dedupe documentation](https://docs.dedupe.io/)
- *Data Matching*, Peter Christen (Springer, 2012). The standard reference on record linkage.
