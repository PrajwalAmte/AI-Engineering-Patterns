---
title: Loop Termination
pillar: loop-engineering
status: validated-in-production
tags: [loops, agents, termination, iteration, control-flow]
related:
  - Token Budget Pattern
  - Circuit Breaker for LLMs
  - No-Progress Detection
  - Reflexion Loop
contributors: ["@PrajwalAmte"]
last_updated: "2026-07"
description: A composite stop-decision — iteration ceiling, goal verification, and no-progress signal — that runs after every step of an agentic loop so it stops for the right reason.
sidebar:
  order: 1
---

## What It Is

The Loop Termination pattern is a single stop-decision function that an agentic loop (reason-act-observe, plan-execute-verify, or any "keep going until done" agent) consults after every step. It combines three independent signals — an iteration ceiling, a goal-verification check, and a no-progress signal — into one gate, rather than relying on any single condition to catch every way a loop can go wrong.

## The Problem It Solves

An agent loop has no natural end unless one is designed in. Left with only one stopping condition, loops fail in predictable ways:

- A token budget alone doesn't catch a loop making many small, cheap calls that never converge — each iteration is inexpensive, so the loop can run for hours without tripping a cost limit.
- An iteration ceiling alone stops the loop eventually, but only after burning the full ceiling even when the agent stalled at iteration 3 of 20.
- A goal check alone (e.g., "did the tests pass?") says nothing about *why* the loop hasn't reached the goal yet, so a stuck loop and a slowly-progressing loop look identical until the ceiling hits.
- No termination logic at all means an interrupted API call, a misread tool result, or a genuinely unsolvable sub-task turns into an unattended loop that runs until something external kills it — a worker timeout, a budget alarm, or a human noticing the bill.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Loop step completes"] --> B{"Goal check: is the task verifiably done?"}
    B -->|"Yes"| C["Terminate: success"]
    B -->|"No"| D{"Iteration ceiling reached?"}
    D -->|"Yes"| E["Terminate: ceiling — return best-effort result or escalate"]
    D -->|"No"| F{"No-progress signal tripped?"}
    F -->|"Yes"| G["Terminate: stalled — return best-effort result or escalate"]
    F -->|"No"| H["Continue: run next iteration"]
    H --> A
</pre>

1. **Define the goal check first.** Before writing any stop logic, define what "done" verifiably means for this loop — a passing test suite, a schema-valid output, an explicit user confirmation. A loop without a checkable goal cannot be terminated correctly; it can only be capped.
2. **Set the iteration ceiling as a backstop, not the primary mechanism.** Choose a ceiling generous enough for legitimate multi-step tasks but tight enough to bound worst-case cost and latency. This is a blunt instrument by design — it exists to guarantee the loop always ends, even if every smarter signal fails to trip.
3. **Wire in a no-progress signal.** Delegate this to the [No-Progress Detection](/AI-Engineering-Patterns/patterns/loop-engineering/no-progress-detection/) pattern so the loop can exit before exhausting its ceiling when it has visibly stalled.
4. **Evaluate all three signals after every iteration, in the same order:** goal check, then ceiling, then no-progress. Checking the goal first means a loop that finishes early exits early, instead of an off-by-one condition on the ceiling forcing one wasted extra step.
5. **Give every non-success exit a defined output.** A loop that hits the ceiling or the no-progress signal should return its best available partial result, escalate to a human, or fail with a structured reason — never just stop silently.

## When to Use It

- Any multi-step agent loop: ReAct-style tool-calling agents, autonomous coding agents, "research until done" pipelines, plan-execute-verify workflows.
- Loops where individual iterations are cheap enough that a token budget alone won't catch runaway iteration count.
- Production systems where unattended loops need a hard cost and latency ceiling regardless of how the loop is performing.

## When NOT to Use It

- Single-shot completions or fixed-length pipelines with a known, deterministic number of steps — there is no open-ended "when do we stop" question to answer.
- Loops that already run inside a durable orchestration framework (Temporal, Step Functions) with its own timeout and retry semantics — duplicate termination logic at both layers creates confusing, conflicting stop reasons.
- Extremely short loops (1-3 iterations) where the overhead of three-signal evaluation exceeds the cost of just letting the loop run to a hardcoded limit.

## Trade-offs

1. **False success risk** — a goal check that's too permissive (e.g., "the code compiles" instead of "the tests pass") lets the loop terminate on a technically-met but practically wrong condition.
2. **Ceiling tuning is task-specific** — a ceiling right for a 3-file refactor is wrong for a 40-file migration; teams often need per-task-class ceilings rather than one global constant.
3. **Escalation paths must exist** — this pattern only decides *when* to stop; if there's no human-review or fallback path wired up for non-success exits, "terminate and escalate" silently becomes "terminate and drop."
4. **Added latency per iteration** — running three checks after every step has a real, if small, cost; for very tight-loop tasks this can matter.

## Failure Modes

### Ceiling Reached Before Goal, No Escalation Path
**Trigger**: The loop hits its iteration ceiling on a genuinely hard task with no human-review or retry-with-more-budget path configured.
**Symptom**: The system silently returns a partial, incorrect, or empty result and the caller has no signal that the loop was cut off rather than having completed successfully.
**Mitigation**: Always tag the termination reason (`success`, `ceiling`, `stalled`, `error`) in the returned result, and require callers to branch on it explicitly rather than treating any returned value as a completed answer.

### Goal Check Too Weak
**Trigger**: The verifiable goal condition checks a proxy for success (e.g., "no exception was thrown") rather than the actual objective (e.g., "the feature works as specified").
**Symptom**: The loop terminates with `success` on outputs that later turn out to be wrong, because the loop was never actually measuring the right thing.
**Mitigation**: Treat the goal check itself as the highest-leverage part of this pattern — invest disproportionately in making it a real verifier (tests, schema validation, an independent grader) rather than a cheap proxy. See the [Maker–Verifier Split](/AI-Engineering-Patterns/patterns/loop-engineering/maker-verifier-split/) pattern for how to keep this check honest.

### Iteration Miscounting
**Trigger**: The system counts logical loop iterations differently from the underlying model calls (e.g., a single "iteration" internally retries a flaky tool call three times without incrementing the counter).
**Symptom**: The loop runs far longer, and costs far more, than the configured ceiling implies.
**Mitigation**: Increment the iteration counter at the single, unambiguous point where the loop decides "take another step," not at every underlying API call.

## Implementation Example

```python
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class StopReason(Enum):
    SUCCESS = "success"
    CEILING = "ceiling"
    STALLED = "stalled"
    ERROR = "error"


@dataclass
class LoopResult:
    output: object
    stop_reason: StopReason
    iterations_used: int


def run_loop(
    step_fn: Callable[[object], object],
    initial_state: object,
    goal_check: Callable[[object], bool],
    no_progress_check: Callable[[list], bool],
    max_iterations: int = 20,
) -> LoopResult:
    state = initial_state
    history = [state]

    for i in range(1, max_iterations + 1):
        state = step_fn(state)
        history.append(state)

        if goal_check(state):
            return LoopResult(state, StopReason.SUCCESS, i)

        if no_progress_check(history):
            return LoopResult(state, StopReason.STALLED, i)

    return LoopResult(state, StopReason.CEILING, max_iterations)


# Example goal check: task-specific verifier, not a cheap proxy
def goal_check(state: dict) -> bool:
    return state.get("tests_passed") is True


# Delegated to the No-Progress Detection Pattern in production;
# shown inline here for a minimal, runnable example
def no_progress_check(history: list, patience: int = 3) -> bool:
    if len(history) < patience + 1:
        return False
    recent = history[-patience:]
    return all(r == recent[0] for r in recent)
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| LangChain / LangGraph | Framework | `max_iterations` and custom graph exit conditions on `AgentExecutor` and `StateGraph` |
| Temporal | Durable execution | Workflow-level timeouts and retry policies; often layered under application-level termination logic |
| AWS Step Functions | Durable execution | State-machine-level iteration limits (`MaxAttempts`, `Iterator` bounds) |
| Custom harnesses (e.g., "Ralph Wiggum"-style loops) | Pattern, not a product | Bare `while` loops around a coding agent with an external spec as the goal check |

## Related Patterns

- **[Token Budget Pattern](/AI-Engineering-Patterns/patterns/cost-and-efficiency/token-budget/)** — bounds cost per request by token count; this pattern bounds the loop by iteration count and goal state, and the two are typically enforced together.
- **[Circuit Breaker for LLMs](/AI-Engineering-Patterns/patterns/reliability/circuit-breaker/)** — protects against downstream failures across many requests; this pattern protects against a single loop running too long.
- **[No-Progress Detection](/AI-Engineering-Patterns/patterns/loop-engineering/no-progress-detection/)** — supplies the no-progress signal this pattern consumes.
- **[Reflexion Loop](/AI-Engineering-Patterns/patterns/loop-engineering/reflexion-loop/)** — a specific loop shape that this pattern's termination logic wraps around.

## Further Reading

- [ReAct: Synergizing Reasoning and Acting in Language Models (Yao et al., 2022)](https://arxiv.org/abs/2210.03629)
- [Loop Engineering for AI Agents — HappyCapy](https://happycapy.ai/blog/loop-engineering-ai-agents)
- [What Is Loop Engineering? — MindStudio](https://www.mindstudio.ai/blog/what-is-loop-engineering-ai-coding-agents)
- [Loop Engineering: The Guide for AI Agents — Lushbinary](https://lushbinary.com/blog/loop-engineering-ai-coding-agents-guide/)