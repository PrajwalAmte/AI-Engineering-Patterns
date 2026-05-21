---
title: Entity Resolution Graph
pillar: graph-patterns
status: emerging
tags: [graph, entity-resolution, deduplication, data-quality, linking]
related:
  - GraphRAG
  - Data Contract Pattern
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Use graph-based approaches to deduplicate, link, and merge entity mentions across heterogeneous data sources into a unified knowledge graph.
sidebar:
  order: 3
---

## What It Is

Entity Resolution Graph is a pattern that uses graph algorithms to identify, link, and merge mentions of the same real-world entity across multiple data sources. Instead of relying purely on string matching or embedding similarity, it models candidate matches as a graph and uses connectivity, transitivity, and community detection to make resolution decisions that individual pairwise comparisons miss.

## The Problem It Solves

AI systems ingest data from many sources. The same entity (customer, product, location, concept) appears with different names, formats, and identifiers across sources:

- "Microsoft Corp", "MSFT", "Microsoft Corporation" in financial data.
- "Dr. Jane Smith", "J. Smith", "jane.smith@hospital.org" in medical records.
- "GPT-4", "gpt-4-turbo", "OpenAI GPT4" in technical documentation.

Without resolution, knowledge graphs have duplicate nodes, RAG systems retrieve fragmented context, and analytics produce wrong counts. Pairwise matching alone fails because:

- It misses transitive links: A matches B, B matches C, but A does not directly match C.
- It cannot use graph structure: an entity connected to the same neighbors is likely the same entity even if names differ.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Mentions from source A"] --> D["Candidate generation (blocking)"]
    B["Mentions from source B"] --> D
    C["Mentions from source C"] --> D
    D --> E["Pairwise similarity scoring"]
    E --> F["Build resolution graph"]
    F --> G["Community detection / clustering"]
    G --> H["Merge cluster into canonical entities"]
    H --> I["Deduplicated entity store"]
</pre>

1. **Extract mentions** — Pull entity mentions from each source with context (surrounding text, metadata, co-occurring entities).
2. **Blocking** — Create candidate pairs using cheap heuristics (same first letter, shared token, locality-sensitive hashing) to avoid O(n^2) comparisons.
3. **Pairwise scoring** — Score candidate pairs using string similarity (Jaro-Winkler, edit distance), embedding cosine similarity, or an LLM-based judge.
4. **Build resolution graph** — Create a graph where nodes are mentions and edges are scored similarities above a threshold.
5. **Community detection** — Run connected components, Louvain clustering, or label propagation to identify clusters of mentions that refer to the same entity.
6. **Merge** — For each cluster, select or synthesize a canonical entity record that combines the best attributes from all mentions.

## When to Use It

- You are building a knowledge graph from multiple data sources and need deduplicated entities.
- Your RAG system retrieves fragmented and contradictory information about the same entity from different documents.
- Analytics or reporting requires accurate entity counts across heterogeneous sources.
- You have long-tail entities (niche products, internal tools, domain-specific terms) that embedding models have not seen.

## When not to Use It

- Entities have reliable unique identifiers across all sources (UUIDs, standardized codes). Simple join-on-ID is cheaper and more accurate.
- The entity space is small and manually curated. A lookup table or alias mapping is simpler and more maintainable.
- Real-time resolution is required. Graph-based approaches are batch-oriented. For real-time, use embedding-based nearest neighbor lookup.

## Trade-offs

1. **Blocking quality** — The blocking strategy determines recall. Aggressive blocking (more pairs) catches more matches but costs more compute. Conservative blocking misses matches.
2. **Threshold sensitivity** — The similarity threshold for creating graph edges controls precision/recall. Too low creates false links; too high misses valid ones.
3. **Transitive errors** — Graph-based approaches propagate errors: one bad edge can merge two unrelated entity clusters.
4. **Maintenance cost** — New data sources require re-running or incrementally updating the resolution pipeline.

## Failure Modes

### Transitive Merge Cascade
**Trigger**: A single incorrect edge links two unrelated entity clusters, and community detection merges them into one super-cluster.
**Symptom**: Hundreds of unrelated entities share a canonical record. Downstream queries get nonsensical answers because the "entity" now represents multiple real-world things.
**Mitigation**: Set a maximum cluster size threshold. Flag clusters that grow beyond expected bounds for manual review. Use edge confidence scores and remove low-confidence edges before community detection.

### Blocking Function Misses Cross-Script Entities
**Trigger**: The blocking function uses first-N characters or phonetic hashing, but entity mentions span multiple scripts or languages ("München" vs. "Munich").
**Symptom**: Valid matches are never generated as candidate pairs because they fall into different blocks. Recall drops silently for multilingual corpora.
**Mitigation**: Use embedding-based blocking that captures semantic similarity across languages. Add transliteration normalization before blocking.

### Stale Canonical After New Source Ingestion
**Trigger**: A new data source provides better-quality entity data than the original canonical, but the pipeline always preserves the first-seen canonical.
**Symptom**: Canonical records remain low-quality even though superior data exists in the cluster. Retrieval surfaces the weaker representation.
**Mitigation**: Re-evaluate canonical selection when new sources are added, using a quality scoring function (completeness, recency, source authority). Allow canonical promotion.

## Implementation Example

```python
from dataclasses import dataclass, field


@dataclass
class EntityMention:
    mention_id: str
    source: str
    name: str
    context: str = ""
    attributes: dict = field(default_factory=dict)


def jaro_winkler_similarity(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    match_distance = max(len1, len2) // 2 - 1
    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (
        matches / len1 + matches / len2 + (matches - transpositions / 2) / matches
    ) / 3
    prefix_len = 0
    for i in range(min(4, min(len1, len2))):
        if s1[i] == s2[i]:
            prefix_len += 1
        else:
            break

    return jaro + prefix_len * 0.1 * (1 - jaro)


class ResolutionGraph:
    def __init__(self, threshold: float = 0.85):
        self._mentions: dict[str, EntityMention] = {}
        self._edges: dict[str, list[tuple[str, float]]] = {}
        self._threshold = threshold

    def add_mention(self, mention: EntityMention) -> None:
        self._mentions[mention.mention_id] = mention
        self._edges[mention.mention_id] = []

    def compute_similarities(self) -> None:
        mention_ids = list(self._mentions.keys())
        for i in range(len(mention_ids)):
            for j in range(i + 1, len(mention_ids)):
                m1 = self._mentions[mention_ids[i]]
                m2 = self._mentions[mention_ids[j]]
                sim = jaro_winkler_similarity(m1.name.lower(), m2.name.lower())
                if sim >= self._threshold:
                    self._edges[mention_ids[i]].append((mention_ids[j], sim))
                    self._edges[mention_ids[j]].append((mention_ids[i], sim))

    def find_clusters(self) -> list[set[str]]:
        visited: set[str] = set()
        clusters: list[set[str]] = []
        for mention_id in self._mentions:
            if mention_id in visited:
                continue
            cluster: set[str] = set()
            queue = [mention_id]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                cluster.add(current)
                for neighbor_id, _ in self._edges.get(current, []):
                    if neighbor_id not in visited:
                        queue.append(neighbor_id)
            clusters.append(cluster)
        return clusters

    def resolve(self) -> list[dict]:
        self.compute_similarities()
        clusters = self.find_clusters()
        resolved = []
        for cluster in clusters:
            mentions = [self._mentions[mid] for mid in cluster]
            canonical = max(mentions, key=lambda m: len(m.name))
            resolved.append({
                "canonical_name": canonical.name,
                "sources": list({m.source for m in mentions}),
                "mention_count": len(mentions),
                "all_names": list({m.name for m in mentions}),
            })
        return resolved
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| Dedupe | Open-source Python | Active learning based entity resolution with blocking |
| Senzing | Commercial | Real-time entity resolution engine with graph-based approach |
| Neo4j + GDS | Graph DB + library | Community detection algorithms (Louvain, WCC) on entity graphs |
| Splink | Open-source (UK Gov) | Probabilistic record linkage at scale with Spark support |
| LLM-based judge | Custom | Use LLM to score whether two mentions refer to the same entity |

## Related Patterns

- **[GraphRAG](/AI-Engineering-Patterns/patterns/graph-patterns/graph-rag/)** — A clean entity-resolved knowledge graph is the foundation for effective GraphRAG.
- **[Data Contract Pattern](/AI-Engineering-Patterns/patterns/data-patterns/data-contract/)** — Data contracts can enforce entity ID standards that reduce the need for resolution.

## Further Reading

- [A Survey of Entity Resolution and Entity Matching](https://arxiv.org/abs/2312.10714)
- [Dedupe Library Documentation](https://docs.dedupe.io/)
- [Splink: Probabilistic Record Linkage at Scale](https://moj-analytical-services.github.io/splink/)
