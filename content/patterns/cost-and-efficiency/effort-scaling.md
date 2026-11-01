---
title: Effort Scaling
pillar: cost-and-efficiency
status: emerging
tags: [cost, agents, budgets, query-complexity]
related:
  - Model Router
  - Multi-Agent Orchestration
  - Token Budget
  - Loop Termination
example: examples/cost_and_efficiency/effort_scaling.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Decide up front how much a task deserves (model, tool calls, sub-agents) and enforce it in code, so fact lookups don't get treated like research projects.
sidebar:
  order: 4
---

## What It Is

Before an agent starts, classify the task into an effort tier, such as *lookup*, *analysis* or *research*. Each tier comes with a budget: which model, how many tool calls, how many sub-agents, how long an answer. The budget is then enforced in code while the task runs, and every run logs predicted against actual effort so the tiers can be recalibrated.

[Model Router](../inference-and-serving/model-router.md) picks *which model*. Effort Scaling picks *how much work*, which for agents is usually the bigger cost.

## The Problem It Solves

Agents are bad at judging effort. Ask a capable research agent "what's our PTO policy?" and it may run twelve searches, spawn sub-agents and write 800 words. Anthropic's write-up of its multi-agent research system names this as an early failure mode: simple queries got far more agents than they needed.

The opposite also happens. A real research question gets a three-search, one-paragraph answer because the agent decided it was done too early.

Prompt instructions ("use fewer tools for simple questions") help a little. A budget the runtime enforces helps a lot.

## How It Works

<pre class="mermaid">
flowchart LR
    T["Task"] --> C["Classify"]
    C -->|"lookup"| L["small model · ≤3 tools · 0 sub-agents"]
    C -->|"analysis"| A["medium model · ≤15 tools · ≤3 sub-agents"]
    C -->|"research"| R["large model · ≤60 tools · ≤8 sub-agents"]
    L & A & R --> E["Run with budget enforced<br/>(exceeding raises, agent must wrap up)"]
    E --> G["Log: tier, used, hit ceiling?, stopped early?"]
    G -.->|"recalibrate"| C
</pre>

1. **Classify cheaply.** Start with rules: comparison words, open-ended words ("research", "landscape"), number of named entities, length. Add a small classifier once you have logged data.
2. **Map tiers to budgets.** Also tell the agent its budget in the prompt. Agents plan better when they know their limits.
3. **Enforce in code.** When the tool-call budget runs out, the next call raises, and the agent must answer with what it has. A sub-agent cap stops fan-out.
4. **Allow early stopping.** A budget is a ceiling, not a target.
5. **Recalibrate from the logs.** Tasks that often hit their ceiling were classified too low. Tasks that consistently use a fraction of their budget were classified too high.

## When to Use It

- Agentic systems where task difficulty varies widely: assistants, research tools, support agents with tools.
- Spend per task varies a lot and isn't explained by task value.
- You already see simple questions getting elaborate treatment.

## When NOT to Use It

- **Uniform tasks.** If every task is a code review of similar size, one budget is fine.
- **Single-call features.** Without tool loops or sub-agents, [Model Router](../inference-and-serving/model-router.md) and [Token Budget](token-budget.md) cover it.

## Trade-offs

- **Misclassification caps quality.** A research question classified as a lookup gets a shallow answer, and the user doesn't know why. Let the agent request an upgrade ("this needs more research") rather than failing silently.
- **Rules go stale.** Phrasing shifts as the product changes. Recalibration from logs is part of the pattern, not an optional extra.
- **Hard stops can produce awkward answers.** An agent cut off mid-plan writes a worse answer than one that knew its budget from the start. Put the budget in the prompt as well as in code.

## Failure Modes

**Everything is "research".** The classifier is tuned to avoid under-serving, so 60% of traffic lands in the top tier and nothing is saved. Watch the tier distribution, and check whether top-tier tasks actually use their budget.

**The budget is only in the prompt.** "Use at most 5 searches" is a suggestion the model will sometimes ignore. Enforce the count in the tool-calling layer.

**No feedback loop.** Tiers are set once and never revisited, while the product's traffic changes. Log predicted against actual effort and review it monthly.

## Implementation Example

A rule-based classifier, tier budgets, a `Run` object that enforces tool and sub-agent limits by raising, and a per-task record for recalibration.

```bash
cd examples && pytest cost_and_efficiency/test_effort_scaling.py
```

<!-- example: examples/cost_and_efficiency/effort_scaling.py -->
```python
"""Effort Scaling.

Decide up front how much a task deserves (model, tool calls, sub-agents,
tokens) and enforce it in code while the task runs. Log predicted vs actual
so the tiers can be recalibrated from data instead of hunches.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Effort:
    tier: str
    model: str
    max_tool_calls: int
    max_subagents: int
    max_output_tokens: int


TIERS = {
    "lookup": Effort("lookup", "small", max_tool_calls=3, max_subagents=0, max_output_tokens=300),
    "analysis": Effort("analysis", "medium", max_tool_calls=15, max_subagents=3, max_output_tokens=1500),
    "research": Effort("research", "large", max_tool_calls=60, max_subagents=8, max_output_tokens=4000),
}

COMPARE = re.compile(r"\b(compare|versus|vs\.?|differences?|trade-?offs?|pros and cons)\b", re.I)
OPEN_ENDED = re.compile(r"\b(research|landscape|survey|comprehensive|all (the )?options|deep dive|strategy)\b", re.I)


def classify(task: str) -> Effort:
    entities = len(re.findall(r"\b[A-Z][a-zA-Z0-9]+\b", task))
    if OPEN_ENDED.search(task) or entities >= 5:
        return TIERS["research"]
    if COMPARE.search(task) or len(task.split()) > 40:
        return TIERS["analysis"]
    return TIERS["lookup"]


class BudgetExhausted(Exception):
    pass


@dataclass
class Run:
    effort: Effort
    tool_calls: int = 0
    subagents: int = 0
    stopped_early: bool = False
    notes: list[str] = field(default_factory=list)

    def tool(self, fn: Callable[..., str], *args) -> str:
        if self.tool_calls >= self.effort.max_tool_calls:
            raise BudgetExhausted(f"{self.effort.tier}: {self.effort.max_tool_calls} tool calls used")
        self.tool_calls += 1
        return fn(*args)

    def spawn(self) -> None:
        if self.subagents >= self.effort.max_subagents:
            raise BudgetExhausted(f"{self.effort.tier}: no more sub-agents allowed")
        self.subagents += 1

    def record(self) -> dict:
        """One row per task: the data you recalibrate tiers from."""
        return {
            "tier": self.effort.tier,
            "tool_calls": self.tool_calls,
            "tool_budget": self.effort.max_tool_calls,
            "subagents": self.subagents,
            "hit_ceiling": self.tool_calls >= self.effort.max_tool_calls,
            "stopped_early": self.stopped_early,
        }
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Reasoning-effort parameters | `reasoning_effort` (OpenAI), extended-thinking budgets (Anthropic), thinking budgets (Gemini): effort scaling for a single call |
| Agent SDK max-turns settings | Hard caps on agent loop iterations |
| LangGraph recursion limit | Graph-level step cap |

## Related Patterns

- [Model Router](../inference-and-serving/model-router.md) chooses the model. This pattern chooses the amount of work.
- [Multi-Agent Orchestration](../inference-and-serving/multi-agent-orchestration.md) is where sub-agent caps matter most.
- [Token Budget](token-budget.md) limits a single prompt. Effort budgets limit the whole task.
- [Loop Termination](../loop-engineering/loop-termination.md): the iteration ceiling there should come from the effort tier.

## Further Reading

- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system), Anthropic, 2025. See the section on scaling effort to query complexity.
- [Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters](https://arxiv.org/abs/2408.03314), Snell et al., 2024
