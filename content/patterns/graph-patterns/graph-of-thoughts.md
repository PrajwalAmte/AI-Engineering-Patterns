---
title: Graph of Thoughts
pillar: graph-patterns
status: emerging
tags: [reasoning, graph, multi-path, planning, llm]
related:
  - GraphRAG
  - Entity Resolution Graph
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Structure LLM reasoning as a directed graph where thoughts branch, merge, and loop to solve complex problems that linear chains cannot.
sidebar:
  order: 2
---

## What It Is

Graph of Thoughts (GoT) structures LLM reasoning as a directed graph rather than a linear chain. Each node is a partial solution or reasoning step. Edges represent transformations — refinement, aggregation, or branching. This allows the model to explore multiple approaches in parallel, merge the best parts, and iteratively refine, producing higher-quality outputs for complex multi-step problems.

## The Problem It Solves

Chain-of-thought (CoT) prompting produces a single linear chain of reasoning. If the model makes a wrong step early, the entire chain follows the wrong path. There is no backtracking, no parallel exploration, and no way to combine partial solutions from different approaches.

- **Sorting a list**: CoT must process linearly. GoT can split the list, sort sub-lists in parallel, and merge.
- **Writing code**: CoT generates one solution. GoT can explore multiple approaches, evaluate each, and combine the best elements.
- **Planning**: CoT commits to one plan. GoT can maintain multiple plan branches and converge on the strongest.

Linear reasoning is a bottleneck for problems that benefit from divide-and-conquer, parallel exploration, or iterative refinement.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Initial problem"] --> B["Decompose into reasoning branches"]
    B --> C1["Branch A: generate partial solution"]
    B --> C2["Branch B: generate partial solution"]
    B --> C3["Branch C: generate partial solution"]
    C1 --> D1["Score A"]
    C2 --> D2["Score B"]
    C3 --> D3["Score C"]
    D1 --> E["Aggregate strongest branches"]
    D2 --> E
    D3 --> E
    E --> F["Refine merged result"]
    F --> G{"Quality threshold met?"}
    G -->|"No"| B
    G -->|"Yes"| H["Final answer"]
</pre>

1. **Decompose** — Break the problem into sub-problems or generate alternative approaches.
2. **Generate** — For each branch, produce a partial solution using the LLM.
3. **Score** — Evaluate each branch using the LLM as a judge or an external evaluator.
4. **Aggregate** — Merge the best branches. Aggregation can be simple selection, weighted combination, or LLM-driven synthesis.
5. **Refine** — Pass the aggregated result through one or more refinement steps.
6. **Repeat** — Loop until a quality threshold is met or a fixed number of iterations complete.

The graph is constructed programmatically by an orchestrator, not by the LLM itself. The LLM is called at each node for generation, scoring, and aggregation.

## When to Use It

- Problems that are naturally decomposable into independent sub-problems (sorting, code generation, document analysis).
- Tasks where exploring multiple approaches and picking the best yields significantly better results than a single linear attempt.
- Scenarios where partial solutions from different approaches can be meaningfully combined.
- Quality-critical tasks where the cost of multiple LLM calls is justified by output quality improvement.

## When not to Use It

- Simple questions with single-step answers. The overhead of graph construction and multiple LLM calls is not justified.
- Latency-sensitive requests. GoT requires multiple sequential and parallel LLM calls, which adds significant latency.
- Tasks where the LLM already achieves near-perfect accuracy with a single call or simple CoT.
- When budget constraints prevent the 3-10x token cost increase over a single call.

## Trade-offs

1. **Token cost** — GoT uses 3-10x more tokens than a single LLM call due to branching, scoring, and aggregation. Each node is a separate inference call.
2. **Latency** — Even with parallel branch execution, the sequential depth of the graph (decompose, generate, score, merge, refine) adds significant latency.
3. **Orchestration complexity** — Building the graph, managing state, handling failures at individual nodes, and implementing the scoring/aggregation logic requires substantial engineering.
4. **Diminishing returns** — For many tasks, Tree-of-Thought or even simple best-of-N sampling achieves most of GoT's quality improvement at lower complexity.

## Failure Modes

### Scoring Function Misalignment
**Trigger**: The scoring LLM evaluates thought nodes on surface-level quality (fluency, length) rather than logical correctness.
**Symptom**: The graph selects confidently wrong branches over tentative but correct ones. Final merged output inherits errors from the highest-scored (but incorrect) paths.
**Mitigation**: Design scoring prompts that explicitly evaluate factual accuracy and logical consistency, not just prose quality. Validate the scorer against a held-out set of known-correct and known-incorrect intermediate steps.

### Merge Step Drops Key Information
**Trigger**: The aggregation prompt that merges solutions from multiple branches has a limited context window and must summarize.
**Symptom**: Critical details from individual branches are lost during merging. The final answer is syntactically coherent but missing nuances that individual branches captured.
**Mitigation**: Use structured extraction from each branch before merging (key claims, numerical results, constraints). Merge from structured data, not raw text.

### Decomposition Explosion
**Trigger**: The decomposition step splits a problem into too many sub-problems, each of which branches further.
**Symptom**: Token costs and latency grow exponentially. Many branches explore trivial or redundant variations. Most of the compute is wasted.
**Mitigation**: Limit branching factor and graph depth. Score sub-problems for independence — discard those that are redundant or trivially solvable. Set a total token budget for the entire GoT execution.

## Implementation Example

```python
from dataclasses import dataclass, field
from enum import Enum


class NodeType(Enum):
    GENERATE = "generate"
    SCORE = "score"
    AGGREGATE = "aggregate"
    REFINE = "refine"


@dataclass
class ThoughtNode:
    node_id: str
    node_type: NodeType
    content: str = ""
    score: float = 0.0
    children: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)


class GraphOfThoughts:
    def __init__(self):
        self._nodes: dict[str, ThoughtNode] = {}
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"node_{self._counter}"

    def add_thought(
        self,
        node_type: NodeType,
        content: str,
        parents: list[str] | None = None,
    ) -> str:
        node_id = self._next_id()
        node = ThoughtNode(
            node_id=node_id,
            node_type=node_type,
            content=content,
            parents=parents or [],
        )
        self._nodes[node_id] = node
        for parent_id in node.parents:
            if parent_id in self._nodes:
                self._nodes[parent_id].children.append(node_id)
        return node_id

    def score_node(self, node_id: str, score: float) -> None:
        self._nodes[node_id].score = score

    def get_top_branches(self, node_ids: list[str], k: int = 2) -> list[str]:
        scored = [(nid, self._nodes[nid].score) for nid in node_ids]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [nid for nid, _ in scored[:k]]

    def get_node(self, node_id: str) -> ThoughtNode:
        return self._nodes[node_id]


def solve_with_got(problem: str, num_branches: int = 3) -> str:
    graph = GraphOfThoughts()
    root = graph.add_thought(NodeType.GENERATE, problem)

    branch_ids = []
    for i in range(num_branches):
        branch_content = f"Approach {i + 1} for: {problem}"
        bid = graph.add_thought(NodeType.GENERATE, branch_content, [root])
        graph.score_node(bid, evaluate_branch(branch_content))
        branch_ids.append(bid)

    top_ids = graph.get_top_branches(branch_ids, k=2)
    top_contents = [graph.get_node(nid).content for nid in top_ids]
    merged = f"Combined solution from: {'; '.join(top_contents)}"
    merge_id = graph.add_thought(NodeType.AGGREGATE, merged, top_ids)

    refined = f"Refined: {merged}"
    graph.add_thought(NodeType.REFINE, refined, [merge_id])
    return refined


def evaluate_branch(content: str) -> float:
    return len(content) / 100.0
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| LangGraph | Framework | Arbitrary graph-based LLM workflows with state management |
| Microsoft AutoGen | Multi-agent framework | Supports branching conversation patterns between agents |
| DSPy | Optimization framework | Composable modules that can implement GoT-style pipelines |
| Custom orchestrator | DIY | Most GoT implementations are bespoke due to problem-specific graph structures |

## Related Patterns

- **[GraphRAG](/AI-Engineering-Patterns/patterns/graph-patterns/graph-rag/)** — Graph structure for retrieval context. GoT is graph structure for reasoning.
- **[Entity Resolution Graph](/AI-Engineering-Patterns/patterns/graph-patterns/entity-resolution-graph/)** — Complementary graph pattern focused on data quality rather than reasoning.

## Further Reading

- [Graph of Thoughts: Solving Elaborate Problems with Large Language Models](https://arxiv.org/abs/2308.09687)
- [Beyond Chain-of-Thought: A Survey of Chain-of-X Paradigms](https://arxiv.org/abs/2404.15676)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
