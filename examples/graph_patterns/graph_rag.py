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
