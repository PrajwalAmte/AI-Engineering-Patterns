---
title: Graph of Thoughts
pillar: graph-patterns
status: emerging
tags: [reasoning, search, aggregation, prompting]
related:
  - Reflexion Loop
  - Maker–Verifier Split
  - Effort Scaling
  - Loop Termination
example: examples/graph_patterns/graph_of_thoughts.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Let a program, not the model, run reasoning as a graph. Generate several candidates, score them, merge the best, refine, and stop on a score or a budget.
sidebar:
  order: 3
---

## What It Is

Chain-of-thought is a line, and Tree-of-Thoughts is a tree: branch, score, prune. Graph of Thoughts (Besta et al., 2023) adds the operation trees lack: **aggregation**, merging several partial solutions into one. With refinement loops on top, the thoughts form a graph.

The orchestrating *program* decides the graph's shape: how many branches, which to keep, when to merge, when to stop. The model is called at each node to generate, merge or refine. Scores ideally come from a programmatic check rather than the model's opinion of itself.

## The Problem It Solves

Some tasks have the property that different attempts get different parts right. One draft sorts the first half correctly, another the second half. One plan handles the edge cases and another has the better structure. Picking the single best attempt throws away the other attempts' good parts. Asking the model to "try again" throws away all of them.

Aggregation keeps them. That's the specific gap this pattern fills, and if your task doesn't have that property, a simpler pattern will do.

## How It Works

<pre class="mermaid">
flowchart TD
    T["Task"] --> G1["Generate #1"]
    T --> G2["Generate #2"]
    T --> G3["Generate #3"]
    G1 & G2 & G3 --> S["Score each<br/>(programmatic check if possible)"]
    S --> K["Keep top k"]
    K --> A["Aggregate: merge the kept thoughts"]
    A --> R["Refine"]
    R --> D{"Score ≥ target<br/>or budget spent?"}
    D -->|"no"| K
    D -->|"yes"| B["Best thought + its lineage"]
</pre>

1. **Generate** several independent candidates. Varying the prompt or the temperature gives you diversity.
2. **Score** each one, with a test, a validator or a metric wherever possible. LLM self-scores are the weakest option.
3. **Keep** the top *k*.
4. **Aggregate** them into one combined candidate, telling the model what each does well.
5. **Refine** the merged result.
6. **Stop** on a score threshold or a hard call budget, and return the best node with its lineage, the graph path that produced it.

## When to Use It

- Tasks where partial solutions can be combined: sorting and merging, set operations, document merging, plan synthesis, code where different attempts pass different tests.
- A reliable scorer exists (tests, validators, metrics).
- Quality matters more than latency and cost: offline jobs, high-value answers.

## When NOT to Use It

- **Interactive latency budgets.** Ten to thirty model calls per answer isn't a chat feature.
- **No reliable scorer.** If scores come from the model rating itself, the graph mostly amplifies its biases. Use a [Maker–Verifier Split](../loop-engineering/maker-verifier-split.md) with an independent check instead.
- **Tasks with one good path.** If attempts don't have complementary strengths, best-of-n sampling is cheaper and just as good.

## Trade-offs

- **Cost multiplies** with branches × rounds × operations. A hard call budget is not optional.
- **Orchestration complexity.** The graph is code you write and maintain per task type. It doesn't generalize for free.
- **Merges can regress.** Aggregation can lose a correct detail from one input. Score after merging, and keep the best-so-far rather than assuming the newest is best.

## Failure Modes

**Score inflation.** The model scores its own merged output highly because it wrote it. Use external scoring, or at least a separate judge prompt that doesn't know which candidate is the merge.

**Diversity collapse.** All branches come back nearly identical, so aggregation has nothing to combine. Vary the instructions per branch (different approaches, not just different random seeds).

**Unbounded refinement.** Each round improves the score by 0.01, so the loop keeps going. Combine the score threshold with a call budget and a [no-progress check](../loop-engineering/no-progress-detection.md).

## Implementation Example

A small GoT controller: generate, score with a pluggable scorer, keep top-k, aggregate, refine, stop on threshold or budget, and return the lineage. In the test, the "model" can only sort halves. No single generation is fully correct, and aggregation produces the correct answer (refine is a no-op, so the credit is clearly the merge's).

```bash
cd examples && pytest graph_patterns/test_graph_of_thoughts.py
```

<!-- example: examples/graph_patterns/graph_of_thoughts.py -->
```python
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
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| spcl/graph-of-thoughts | Reference implementation from the paper's authors |
| LangGraph | General graph orchestration to build GoT-style controllers |
| DSPy | Programmatic pipelines with optimizable modules; good for scorers and refiners |

## Related Patterns

- [Reflexion Loop](../loop-engineering/reflexion-loop.md) improves one line of attempts with lessons learned. GoT combines many attempts.
- [Maker–Verifier Split](../loop-engineering/maker-verifier-split.md) is the right way to get scores you can trust.
- [Effort Scaling](../cost-and-efficiency/effort-scaling.md) decides which tasks deserve a GoT budget at all.
- [Loop Termination](../loop-engineering/loop-termination.md) applies to the refinement loop.

## Further Reading

- [Graph of Thoughts: Solving Elaborate Problems with Large Language Models](https://arxiv.org/abs/2308.09687), Besta et al., 2023
- [Tree of Thoughts: Deliberate Problem Solving with Large Language Models](https://arxiv.org/abs/2305.10601), Yao et al., 2023
