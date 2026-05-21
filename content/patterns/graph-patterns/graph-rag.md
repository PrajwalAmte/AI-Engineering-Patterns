---
title: GraphRAG
pillar: graph-patterns
status: validated-in-production
tags: [graph, rag, knowledge-graph, retrieval, multi-hop]
related:
  - Hybrid Search
  - Entity Resolution Graph
  - Graph of Thoughts
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Augment RAG with knowledge graphs for multi-hop reasoning, entity relationships, and structured context that vector search alone cannot provide.
sidebar:
  order: 1
---

## What It Is

GraphRAG combines traditional vector-based retrieval with a knowledge graph to provide structured, relationship-aware context to LLMs. Instead of retrieving isolated text chunks, GraphRAG traverses entity relationships in a graph to assemble context that spans multiple documents and captures how concepts connect.

## The Problem It Solves

Standard RAG retrieves chunks of text that are semantically similar to the query. This works for factual lookups but breaks down when the answer requires connecting information across multiple documents or understanding relationships between entities.

- "Which team members have worked on projects that use the same technology stack?" requires joining person-project-technology relationships.
- "What are the downstream effects of deprecating Service X?" requires traversing a dependency graph.
- "Compare the approaches used by Team A and Team B for authentication" requires pulling and connecting information from separate sources.

Vector similarity alone cannot express graph traversals, joins, or multi-hop reasoning.

## How It Works

<pre class="mermaid">
flowchart TD
    A["User query"] --> B["Entity extraction"]
    A --> C["Vector retrieval"]
    B --> D["Knowledge graph traversal"]
    D --> E["Graph facts and relationships"]
    C --> F["Unstructured passages"]
    E --> G["Context assembly"]
    F --> G
    G --> H["LLM generation"]
    H --> I["Answer"]
</pre>

1. **Entity extraction** — Extract entities and intent from the query using NER or an LLM.
2. **Graph traversal** — Look up extracted entities in the knowledge graph and traverse relationships to gather structured context (neighbors, paths, subgraphs).
3. **Vector retrieval** — Run standard embedding search in parallel for unstructured context.
4. **Context assembly** — Merge graph-derived facts (entity properties, relationships, paths) with vector-retrieved passages into a structured prompt.
5. **Generation** — Send the enriched context to the LLM for answer generation.

The knowledge graph can be prebuilt from documents using an entity extraction pipeline, or maintained as a curated knowledge base.

## When to Use It

- Queries frequently require connecting information across multiple documents.
- Your domain has clear entity relationships (org charts, dependency maps, product catalogs, medical knowledge bases).
- Users ask comparative, relational, or multi-hop questions.
- You need explainable retrieval — the graph traversal path shows why certain context was included.
- Standard RAG recall is poor for relationship queries despite good chunk quality.

## When not to Use It

- Queries are simple factual lookups that vector search handles well. GraphRAG adds significant complexity for marginal improvement on single-hop questions.
- You do not have clean, structured data to build a knowledge graph from. Garbage-in-garbage-out applies even more to graphs than to vector stores.
- The knowledge base changes so frequently that maintaining a graph is impractical. Graph construction and updates are expensive.
- Your team cannot invest in graph infrastructure (Neo4j, Neptune, or similar) and the associated operational overhead.

## Trade-offs

1. **Graph construction cost** — Building and maintaining a knowledge graph from unstructured documents requires an entity extraction pipeline, which introduces its own error rate and latency.
2. **Query routing complexity** — Not every query benefits from graph traversal. You need a router to decide when to activate the graph path vs. pure vector retrieval.
3. **Staleness risk** — The knowledge graph can drift from source documents if the extraction pipeline is not run on every update.
4. **Infrastructure overhead** — Requires a graph database in addition to the vector store. Two systems to maintain, monitor, and back up.

## Failure Modes

### Entity Extraction Hallucination
**Trigger**: The extraction pipeline (often an LLM) hallucinates entities or relationships during knowledge graph construction.
**Symptom**: The graph contains phantom nodes and edges. Queries that traverse these edges return confident but fabricated answers grounded in non-existent relationships.
**Mitigation**: Validate extracted triples against source documents. Use extraction confidence scores and discard low-confidence triples. Periodically audit random graph subsets.

### Over-Traversal on Vague Queries
**Trigger**: A broad or ambiguous query causes the graph traversal to fan out through many hops, pulling in loosely related context.
**Symptom**: Context window fills with tangentially related graph output. The LLM produces verbose, unfocused answers. Latency spikes from deep traversal.
**Mitigation**: Set a maximum traversal depth and node limit per query. Score relevance at each hop and prune low-relevance paths. Fall back to vector search for queries that do not map cleanly to entity lookups.

### Graph Staleness After Source Update
**Trigger**: Source documents are updated but the knowledge graph extraction pipeline runs on a schedule (daily, weekly) rather than in real-time.
**Symptom**: Graph contains outdated relationships. A vector search might return updated content, but the graph path retrieves stale context, creating contradictions in the prompt.
**Mitigation**: Track source document versions in graph metadata. Flag graph nodes whose source has been modified since extraction. Prioritize re-extraction of flagged subgraphs.

## Implementation Example

```python
from dataclasses import dataclass, field


@dataclass
class Entity:
    name: str
    entity_type: str
    properties: dict = field(default_factory=dict)


@dataclass
class Relationship:
    source: str
    target: str
    relation_type: str
    properties: dict = field(default_factory=dict)


class KnowledgeGraph:
    def __init__(self):
        self._entities: dict[str, Entity] = {}
        self._adjacency: dict[str, list[Relationship]] = {}

    def add_entity(self, entity: Entity) -> None:
        self._entities[entity.name] = entity
        if entity.name not in self._adjacency:
            self._adjacency[entity.name] = []

    def add_relationship(self, rel: Relationship) -> None:
        if rel.source not in self._adjacency:
            self._adjacency[rel.source] = []
        self._adjacency[rel.source].append(rel)

    def get_neighbors(self, entity_name: str, max_depth: int = 2) -> list[dict]:
        visited: set[str] = set()
        results: list[dict] = []
        queue: list[tuple[str, int]] = [(entity_name, 0)]

        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)

            for rel in self._adjacency.get(current, []):
                results.append({
                    "source": current,
                    "relation": rel.relation_type,
                    "target": rel.target,
                    "depth": depth,
                })
                if rel.target not in visited:
                    queue.append((rel.target, depth + 1))

        return results

    def get_entity(self, name: str) -> Entity | None:
        return self._entities.get(name)


def extract_entities(query: str) -> list[str]:
    return [token for token in query.split() if token[0].isupper()]


def build_graph_context(
    graph: KnowledgeGraph,
    entities: list[str],
    max_depth: int = 2,
) -> str:
    context_lines = []
    for entity_name in entities:
        entity = graph.get_entity(entity_name)
        if not entity:
            continue
        context_lines.append(f"Entity: {entity.name} ({entity.entity_type})")
        neighbors = graph.get_neighbors(entity_name, max_depth)
        for rel in neighbors:
            context_lines.append(
                f"  {rel['source']} --[{rel['relation']}]--> {rel['target']}"
            )
    return "\n".join(context_lines)


def graph_rag_query(
    query: str,
    graph: KnowledgeGraph,
    vector_results: list[str],
) -> str:
    entities = extract_entities(query)
    graph_context = build_graph_context(graph, entities)
    vector_context = "\n".join(vector_results)
    prompt = (
        f"Answer the following question using the provided context.\n\n"
        f"Graph Context (entity relationships):\n{graph_context}\n\n"
        f"Document Context (retrieved passages):\n{vector_context}\n\n"
        f"Question: {query}"
    )
    return prompt
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| Neo4j + LangChain | Graph DB + framework | Native Cypher queries combined with LLM chains |
| Microsoft GraphRAG | Open-source library | Builds community summaries from documents, designed for global queries |
| Amazon Neptune | Managed graph DB | Enterprise-grade, integrates with AWS Bedrock for LLM |
| FalkorDB | Open-source graph DB | Low-latency graph queries optimized for RAG workloads |
| LlamaIndex Knowledge Graph | Framework | Property graph index with automatic entity extraction |

## Related Patterns

- **[Hybrid Search](/AI-Engineering-Patterns/patterns/retrieval-and-memory/hybrid-search/)** — Combine with GraphRAG for both semantic and structural retrieval.
- **[Entity Resolution Graph](/AI-Engineering-Patterns/patterns/graph-patterns/entity-resolution-graph/)** — Clean entity data is a prerequisite for a useful knowledge graph.
- **[Graph of Thoughts](/AI-Engineering-Patterns/patterns/graph-patterns/graph-of-thoughts/)** — Graph reasoning at inference time complements graph-structured retrieval.

## Further Reading

- [Microsoft GraphRAG Paper](https://arxiv.org/abs/2404.16130)
- [GraphRAG: Unlocking LLM Discovery on Narrative Private Data](https://www.microsoft.com/en-us/research/blog/graphrag-unlocking-llm-discovery-on-narrative-private-data/)
- [Neo4j GraphRAG Python Package](https://neo4j.com/docs/neo4j-graphrag-python/current/)
