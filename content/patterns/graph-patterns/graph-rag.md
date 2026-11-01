---
title: GraphRAG
pillar: graph-patterns
status: validated-in-production
tags: [rag, knowledge-graph, multi-hop, retrieval]
related:
  - Hybrid Search
  - Entity Resolution Graph
  - Grounding Verifier
  - Retrieval Freshness Watermark
example: examples/graph_patterns/graph_rag.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: For questions about relationships, find the entities in the question, walk the knowledge graph a few hops, and give the model the facts and paths with their sources.
sidebar:
  order: 1
---

## What It Is

Retrieval over a knowledge graph instead of, or alongside, text chunks. Entities in the question are matched to graph nodes, the graph is walked a few hops out, and the facts found ("checkout-service depends on payments-db", "checkout-service is owned by Team Orion") go into the prompt with their sources.

"GraphRAG" covers two related things:

- **Local search**, shown here: start from the entities in a question and traverse their neighborhood. This suits specific questions about how things relate.
- **Global search**, popularized by Microsoft's GraphRAG: cluster the graph into communities, pre-summarize each one, and answer broad "what are the main themes?" questions from the summaries.

## The Problem It Solves

Vector search finds text that is *similar* to the question. Some questions need facts that are *connected* to it instead. "Which teams are affected if the payments database goes down?" requires following *depends on* from the database to services, then *owned by* from services to teams. No single chunk contains that answer, and the chunks that do contain pieces of it don't look like the question.

Text retrieval tends to return the payments-db runbook and stop there. The model then guesses the rest, or says it doesn't know.

## How It Works

<pre class="mermaid">
flowchart LR
    Q["Question"] --> E["Find entities<br/>(names + aliases → nodes)"]
    E --> T["Traverse k hops, both directions,<br/>closest facts first, capped"]
    Q --> V["Text retrieval (optional)"]
    T --> C["Context: facts with sources<br/>+ passages"]
    V --> C
    C --> L["Model: follow the relations step by step"]
</pre>

1. **Build the graph** from structured sources you already have (service catalogs, ownership files, CRM), from LLM extraction over documents, or both. Structured sources are far more reliable. Start there.
2. **Link the question to nodes.** Exact and alias matching gets surprisingly far for internal entities. Use NER or an LLM for open-ended text.
3. **Traverse breadth-first,** in both edge directions, up to *k* hops (two or three is typical), with a cap on facts so hub nodes don't flood the prompt.
4. **Put facts in the prompt as short lines with sources,** so the model can cite them and a [Grounding Verifier](../retrieval-and-memory/grounding-verifier.md) can check them.
5. **Combine with text retrieval** when the question also needs prose: why something is the way it is, or how to fix it.

## When to Use It

- Questions are about dependencies, ownership, org structure, supply chains, citations, or anything with "who/what is connected to…".
- You already have relationship data in structured form, or can extract it reliably.
- Plain RAG answers these questions by guessing.

## When NOT to Use It

- **Questions are mostly "what does the document say about X"?** That's text retrieval. A graph adds cost and moving parts.
- **No reliable source of relationships.** A graph built from noisy LLM extraction gives confidently wrong answers that look authoritative. Measure extraction precision before relying on it.
- **Global summarization over a small corpus.** If everything fits in context, summarize directly.

## Trade-offs

- **Building and maintaining the graph is the real cost.** Extraction pipelines, [entity resolution](entity-resolution-graph.md), keeping it in sync with the sources. Querying is the easy part.
- **Hubs explode.** A node like "AWS" or "Engineering" connects to everything. Cap facts, weight by relation type, or exclude hub nodes from traversal.
- **Hop count is a precision/recall dial.** One hop misses the answer and three hops drags in noise. Tune it per question type if you can.

## Failure Modes

**Duplicate entities break paths.** "Payments DB", "payments-db" and "PaymentsDatabase" are three nodes, and the traversal from one never reaches facts attached to the others. Resolve entities before building edges ([Entity Resolution Graph](entity-resolution-graph.md)).

**Stale edges.** The ownership file changed last month and the graph didn't. Answers are now confidently wrong. Attach sources and dates to edges and rebuild from source on a schedule ([Retrieval Freshness Watermark](../retrieval-and-memory/retrieval-freshness-watermark.md)).

**Facts without sources.** The model states a relationship, and nobody can tell whether it came from the graph or from the model's imagination. Always render facts with their source.

## Implementation Example

Alias-aware entity linking, capped breadth-first traversal in both directions, and fact lines with sources. The test asks an ownership question that needs two hops, and confirms one hop isn't enough.

```bash
cd examples && pytest graph_patterns/test_graph_rag.py
```

<!-- example: examples/graph_patterns/graph_rag.py -->
```python
"""GraphRAG (local search).

For questions about *relationships* ("which teams are affected if the
payments DB goes down?"), find the entities in the question, walk the
knowledge graph a few hops out, and give the model the facts and paths it
found alongside any text passages. Vector search finds similar text; it
can't follow "depends on" twice.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Triple:
    subject: str
    relation: str
    object: str
    source: str = ""  # document the fact came from, for citations


@dataclass
class KnowledgeGraph:
    triples: list[Triple] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)  # lowercase alias -> canonical name

    def __post_init__(self):
        self.out_edges: dict[str, list[Triple]] = defaultdict(list)
        self.in_edges: dict[str, list[Triple]] = defaultdict(list)
        for t in self.triples:
            self.add(t)

    def add(self, t: Triple) -> None:
        if t not in self.out_edges[t.subject]:
            self.out_edges[t.subject].append(t)
            self.in_edges[t.object].append(t)
        for name in (t.subject, t.object):
            self.aliases.setdefault(name.lower(), name)

    def entities_in(self, text: str) -> list[str]:
        """Longest-match lookup of known names and aliases. Swap for NER/LLM extraction at scale."""
        found, lowered = [], text.lower()
        for alias in sorted(self.aliases, key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", lowered) and self.aliases[alias] not in found:
                found.append(self.aliases[alias])
                lowered = lowered.replace(alias, " ")
        return found

    def neighbourhood(self, seeds: list[str], hops: int = 2, max_facts: int = 30) -> list[Triple]:
        """Breadth-first over both edge directions, closest facts first, capped."""
        seen_nodes, facts = set(seeds), []
        queue = deque((s, 0) for s in seeds)
        while queue and len(facts) < max_facts:
            node, depth = queue.popleft()
            if depth == hops:
                continue
            for t in self.out_edges[node] + self.in_edges[node]:
                if t not in facts:
                    facts.append(t)
                nxt = t.object if t.subject == node else t.subject
                if nxt not in seen_nodes:
                    seen_nodes.add(nxt)
                    queue.append((nxt, depth + 1))
        return facts[:max_facts]


def build_context(question: str, kg: KnowledgeGraph, passages: list[str], hops: int = 2) -> str:
    seeds = kg.entities_in(question)
    facts = kg.neighbourhood(seeds, hops=hops)
    lines = [f"Entities in question: {', '.join(seeds) or 'none found'}", "Known facts:"]
    lines += [f"- {t.subject} {t.relation} {t.object}" + (f" [{t.source}]" if t.source else "") for t in facts]
    if passages:
        lines += ["Related passages:", *[f"- {p}" for p in passages]]
    return "\n".join(lines)


def answer(question: str, kg: KnowledgeGraph, llm: Callable[[str], str], passages: list[str] = ()) -> str:
    context = build_context(question, kg, list(passages))
    return llm(f"Answer from the facts below. Follow relationships step by step.\n\n{context}\n\nQ: {question}")
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Microsoft GraphRAG | Community detection and pre-summarization for global questions |
| Neo4j + neo4j-graphrag | Graph database with retrievers that mix vector and Cypher traversal |
| LlamaIndex PropertyGraphIndex | Build and query property graphs from documents |
| LightRAG | Lightweight graph-plus-vector retrieval |

## Related Patterns

- [Hybrid Search](../retrieval-and-memory/hybrid-search.md) handles text. Combine the two when questions need facts *and* prose.
- [Entity Resolution Graph](entity-resolution-graph.md) is what keeps the graph from fragmenting.
- [Grounding Verifier](../retrieval-and-memory/grounding-verifier.md) checks that the answer's claims match the facts provided.
- [Retrieval Freshness Watermark](../retrieval-and-memory/retrieval-freshness-watermark.md): edges go stale too.

## Further Reading

- [From Local to Global: A Graph RAG Approach to Query-Focused Summarization](https://arxiv.org/abs/2404.16130), Edge et al. (Microsoft), 2024
- [GraphRAG: Unlocking LLM discovery on narrative private data](https://www.microsoft.com/en-us/research/blog/graphrag-unlocking-llm-discovery-on-narrative-private-data/), Microsoft Research
- [Neo4j GraphRAG for Python](https://neo4j.com/docs/neo4j-graphrag-python/current/)
