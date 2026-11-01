"""Graph of Thoughts.

Reasoning as an explicit graph that the *program* controls: generate several
candidate thoughts, score them, keep the best, merge them (the operation
chains and trees don't have), refine, and stop on a score threshold or a call
budget. The LLM is called at each node; it never decides the graph's shape.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

LLM = Callable[[str], str]
Scorer = Callable[[str], float]  # prefer a programmatic check over an LLM score when one exists


@dataclass
class Thought:
    id: int
    text: str
    score: float
    parents: list[int] = field(default_factory=list)
    op: str = "generate"


@dataclass
class GraphOfThoughts:
    llm: LLM
    score: Scorer
    branches: int = 3
    keep: int = 2
    max_rounds: int = 3
    good_enough: float = 0.95
    max_calls: int = 30
    nodes: list[Thought] = field(default_factory=list)
    calls: int = 0

    def _call(self, prompt: str) -> str:
        if self.calls >= self.max_calls:
            raise RuntimeError("thought budget exhausted")
        self.calls += 1
        return self.llm(prompt)

    def _add(self, text: str, parents: list[int], op: str) -> Thought:
        t = Thought(len(self.nodes), text, self.score(text), parents, op)
        self.nodes.append(t)
        return t

    def solve(self, task: str) -> Thought:
        frontier = [self._add(self._call(f"GENERATE #{i}\n{task}"), [], "generate") for i in range(self.branches)]
        best = max(frontier, key=lambda t: t.score)
        try:
            for _ in range(self.max_rounds):
                if best.score >= self.good_enough:
                    break
                top = sorted(frontier, key=lambda t: -t.score)[: self.keep]
                merged = self._add(
                    self._call("AGGREGATE\n" + task + "\n" + "\n---\n".join(t.text for t in top)),
                    [t.id for t in top],
                    "aggregate",
                )
                refined = self._add(self._call(f"REFINE\n{task}\n{merged.text}"), [merged.id], "refine")
                frontier = top + [merged, refined]
                best = max(frontier + [best], key=lambda t: t.score)
        except RuntimeError:
            pass  # out of budget: return the best thought so far
        return best

    def lineage(self, thought: Thought) -> list[str]:
        """How the answer was reached; useful for debugging and for showing work."""
        out, stack = [], [thought.id]
        while stack:
            t = self.nodes[stack.pop()]
            out.append(f"#{t.id} {t.op} score={t.score:.2f}")
            stack.extend(t.parents)
        return out
