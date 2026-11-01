---
title: Loop Termination
pillar: loop-engineering
status: validated-in-production
tags: [agents, loops, termination, budgets]
related:
  - No-Progress Detection
  - Maker–Verifier Split
  - Effort Scaling
  - Semantic Rollback
example: examples/loop_engineering/loop_termination.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: One stop decision checked after every step (goal met, ceiling reached, or stalled), and every non-success exit returns the best result so far with a reason.
sidebar:
  order: 1
---

## What It Is

An agent loop (reason → act → observe, or plan → execute → verify) has no natural end. This pattern gives it one: a single stop decision, run after every step, that checks three signals in a fixed order:

1. **Goal check.** Is the task verifiably done? Stop: success.
2. **Ceiling.** Out of iterations, or out of cost or time budget? Stop: ceiling.
3. **No progress.** Has the loop plateaued or started oscillating? Stop: stalled.

Every exit that isn't success returns the best result seen so far and a reason. The loop never just stops.

## The Problem It Solves

Each signal alone fails in a predictable way:

- **Only an iteration cap.** A loop stuck at step 3 burns all 20 iterations before stopping.
- **Only a cost cap.** Many small, cheap steps never reach the cap and run for hours.
- **Only a goal check.** You can't tell "stuck" from "slowly getting there" until something external kills the process.
- **No logic at all.** A misread tool result becomes an unattended loop that runs until a worker timeout or a billing alert.

## How It Works

<pre class="mermaid">
flowchart TD
    S["Step completes"] --> G{"Goal verifiably met?"}
    G -->|"yes"| OK["Stop: success"]
    G -->|"no"| C{"Iteration / cost /<br/>time ceiling hit?"}
    C -->|"yes"| CE["Stop: ceiling → best result + reason"]
    C -->|"no"| P{"Plateau or oscillation?"}
    P -->|"yes"| ST["Stop: stalled → best result + reason"]
    P -->|"no"| N["Next step"]
    N --> S
</pre>

1. **Define "done" as something checkable** before writing any loop: tests pass, the output validates against a schema, the user confirms. If "done" means "the agent says it's done", see [Maker–Verifier Split](maker-verifier-split.md).
2. **Treat the ceilings as backstops.** Set them generously enough for real tasks and tightly enough to bound the worst-case bill. [Effort Scaling](../cost-and-efficiency/effort-scaling.md) can set them per task.
3. **Plug in [No-Progress Detection](no-progress-detection.md)** so stalled loops exit early.
4. **Check in a fixed order, with the goal first,** so a loop that succeeds on its final allowed step is reported as a success, not a ceiling exit.
5. **Give each exit a defined output:** the best partial result, a structured reason, and an escalation path.

## When to Use It

- Any agent loop that runs without a human watching each step: coding agents, research agents, data pipelines with LLM steps.
- Loops whose cost is open-ended.

## When NOT to Use It

- **Single model calls.** There's no loop.
- **Fixed pipelines** with a known number of steps. Those are workflows, not loops.

## Trade-offs

- **Ceilings cut off some legitimate long tasks.** Log ceiling exits and review them. A cluster of them on one task type means its ceiling is too low.
- **Stall detection can stop a loop that was about to break through.** Use patience windows and return the best result so the work isn't lost.
- **Goal checks cost something.** Running a test suite every iteration adds time. Run cheap checks every step and expensive ones when the agent claims it's done.

## Failure Modes

**"Done" means the agent said so.** The agent declares victory and the loop exits with a broken result reported as success. Use a mechanical goal check or an independent verifier.

**Silent ceiling exits.** The loop hits 20 iterations and returns the last output with no indication. Downstream code treats it as an answer. Always return the stop reason, and handle non-success explicitly.

**The last output isn't the best one.** Oscillating loops end on whichever state came last. Track scores and return the best.

## Implementation Example

The three checks in order, cost and iteration ceilings, stall detection from the [No-Progress Detection](no-progress-detection.md) example, and best-result tracking. The tests cover success on the final step, early exit on a stall, a cheap-but-endless loop caught by budget, and returning the best result rather than the last.

```bash
cd examples && pytest loop_engineering/test_loop_termination.py
```

<!-- example: examples/loop_engineering/loop_termination.py -->
```python
"""Loop Termination.

One stop decision, checked after every step, in a fixed order:
1. goal check   -> stop: success
2. ceiling      -> stop: out of iterations or budget
3. no progress  -> stop: stalled
Every non-success stop returns the best result so far and a reason, so the
caller can show partial work or escalate instead of failing silently.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from loop_engineering.no_progress_detection import ProgressMonitor


@dataclass
class Outcome:
    reason: str  # "success" | "ceiling" | "budget" | "stalled"
    iterations: int
    result: str
    cost: float


def run_loop(
    step: Callable[[int, str | None], tuple[str, float]],  # (iteration, last_output) -> (output, cost)
    goal_met: Callable[[str], bool],
    max_iterations: int = 20,
    max_cost: float = float("inf"),
    monitor: ProgressMonitor | None = None,
    score: Callable[[str], float] | None = None,
) -> Outcome:
    monitor = monitor or ProgressMonitor()
    output, spent = None, 0.0
    for i in range(1, max_iterations + 1):
        output, cost = step(i, output)
        spent += cost
        trend = monitor.observe(output, score(output) if score else None)

        if goal_met(output):  # goal first: finishing on the last allowed step is still success
            return Outcome("success", i, output, spent)
        if spent >= max_cost:
            return Outcome("budget", i, monitor.best(), spent)
        if trend in ("plateau", "oscillating"):
            return Outcome("stalled", i, monitor.best(), spent)
    return Outcome("ceiling", max_iterations, monitor.best(), spent)
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Agent SDK max-turns settings | Iteration ceiling (Claude Agent SDK, OpenAI Agents SDK) |
| LangGraph `recursion_limit` | Step ceiling on graph execution |
| Your gateway budgets | Cost ceiling enforced outside the agent |

## Related Patterns

- [No-Progress Detection](no-progress-detection.md) supplies the stall signal.
- [Maker–Verifier Split](maker-verifier-split.md) makes the goal check trustworthy.
- [Effort Scaling](../cost-and-efficiency/effort-scaling.md) sets ceilings based on what the task deserves.
- [Semantic Rollback](semantic-rollback.md) handles failures *inside* the loop without restarting it.

## Further Reading

- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629), Yao et al., 2022
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), Anthropic, 2024. On stopping conditions and guardrails for autonomous loops.
