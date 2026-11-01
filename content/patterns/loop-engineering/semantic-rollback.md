---
title: Semantic Rollback
pillar: loop-engineering
status: emerging
tags: [agents, checkpoints, recovery, workflows]
related:
  - Loop Termination
  - No-Progress Detection
  - Maker–Verifier Split
  - Circuit Breaker for LLMs
example: examples/loop_engineering/semantic_rollback.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Checkpoint a multi-step workflow after each validated step. When a step fails or produces junk, restore the last good state and retry that step with a different strategy.
sidebar:
  order: 5
---

## What It Is

A multi-step agent workflow (plan → fetch → analyze → write) is run as named steps. After each step, its result is *validated*. If it's valid, the state is checkpointed. If a step throws or produces something invalid, the workflow restores the last checkpoint, discarding anything the bad step wrote, and retries *that step*, telling it which attempt this is so it can change approach. After N attempts it stops, returning the last good state and naming the failed step.

"Semantic" because checkpoints mark points where the work makes sense, not arbitrary positions in the code. Durable-execution engines (Temporal, LangGraph checkpointers) give you checkpoint and replay. This pattern adds a semantic validation gate and strategy-changing retries on top.

## The Problem It Solves

Long agent workflows fail partway through, and the two default reactions are both bad:

- **Restart from scratch** and throw away three good steps of research because step four timed out.
- **Continue with corrupt state:** step four returned an empty or wrong result, steps five to eight build on it, and the final report is fluent nonsense.

A third problem is subtler: a failed attempt often leaves partial writes in the shared state, such as a half-downloaded file or a scratch variable. Retrying on top of that debris causes new failures that have nothing to do with the original one.

## How It Works

<pre class="mermaid">
flowchart TD
    C["Last checkpoint"] --> R["Run step (attempt n)<br/>on a copy of the checkpoint"]
    R --> V{"Raised, or failed validation?"}
    V -->|"no"| K["Save as new checkpoint → next step"]
    V -->|"yes"| A{"Attempts left?"}
    A -->|"yes"| C2["Discard the copy, restore checkpoint,<br/>retry with attempt n+1 (new strategy)"]
    C2 --> R
    A -->|"no"| F["Stop: last good state + failed step name"]
</pre>

1. **Name the steps and give each a validator,** something checkable: non-empty, matches a schema, passes a test, or approved by a [verifier](maker-verifier-split.md).
2. **Run each attempt on a copy** of the last checkpoint, so failed attempts can't leave anything behind.
3. **Pass the attempt number to the step.** Retrying identically usually reproduces the failure. Attempt 2 should do something different: a narrower query, another tool, a different prompt.
4. **Cap attempts per step,** then stop with a clear result: what completed, what failed, and the state to resume from.

## When to Use It

- Workflows of several steps where later steps depend on earlier ones.
- Steps that are expensive to redo (long research, paid API calls, user-visible latency).
- Steps that fail transiently (timeouts) or produce sometimes-invalid output (empty results, bad JSON).

## When NOT to Use It

- **Single-step calls.** There's nothing to checkpoint.
- **Cheap workflows,** where restarting from scratch costs less than the bookkeeping.
- **Steps with external side effects that can't be undone.** Restoring *your* state doesn't un-send an email. Put those steps behind [Human-in-the-Loop](../governance/human-in-the-loop.md), or make them idempotent and place them last.

## Trade-offs

- **Checkpoint cost.** Copying large state at every step costs memory and storage. Store deltas or references for big artifacts.
- **Validators are the weak point.** A validator that passes junk creates a "good" checkpoint full of junk. Invest in validators more than in checkpoint frequency.
- **Retries change behavior.** Strategy-changing retries are the point, but they make runs less reproducible. Log which strategy produced each checkpoint.

## Failure Modes

**Identical retries.** The step ignores the attempt number and fails the same way three times. This was the bug in this page's earlier example, where the rollback happened but the step was never re-run with anything new. Make strategy changes explicit.

**Debris from failed attempts.** A retry runs on state the failed attempt modified. Always restore from a copy. The example's test checks that scratch keys from failed attempts don't survive.

**Rolling back external effects you can't undo.** Local state goes back, the outside world doesn't. Mark side-effecting steps, and never retry them automatically without idempotency keys.

## Implementation Example

Named steps with validators, copy-on-attempt state, a checkpoint after each valid step, retries that pass the attempt number, a per-step attempt cap, and a log of rollbacks. The tests cover a timeout that succeeds on retry, an empty result treated as invalid, a strategy change, and giving up while keeping the last good state.

```bash
cd examples && pytest loop_engineering/test_semantic_rollback.py
```

<!-- example: examples/loop_engineering/semantic_rollback.py -->
```python
"""Semantic Rollback.

Run a multi-step workflow as named steps. After each step, validate the
result; if valid, checkpoint. If a step fails or produces something invalid,
restore the last checkpoint (dropping anything the bad step wrote) and retry
that step with the attempt number, so the step can change strategy. After N
failed attempts, stop with the last good state and say which step failed.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field

State = dict  # whatever the workflow carries between steps
StepFn = Callable[[State, int], object]  # (state, attempt) -> value; attempt starts at 1
Validator = Callable[[State, object], str | None]  # -> problem description, or None if fine


@dataclass
class Step:
    name: str
    run: StepFn
    validate: Validator = lambda state, value: None if value not in (None, "", [], {}) else "empty result"


@dataclass
class RunResult:
    completed: bool
    state: State
    failed_step: str | None = None
    log: list[str] = field(default_factory=list)


def run_workflow(steps: list[Step], initial: State, max_attempts: int = 3) -> RunResult:
    checkpoint = copy.deepcopy(initial)
    log: list[str] = []

    for step in steps:
        for attempt in range(1, max_attempts + 1):
            state = copy.deepcopy(checkpoint)  # every attempt starts from the last good state
            try:
                value = step.run(state, attempt)
                problem = step.validate(state, value)
            except Exception as exc:
                problem = f"{type(exc).__name__}: {exc}"
            if problem is None:
                state[step.name] = value
                checkpoint = state
                log.append(f"{step.name}: ok on attempt {attempt} (checkpoint)")
                break
            log.append(f"{step.name}: attempt {attempt} rejected ({problem}); rolled back")
        else:
            return RunResult(False, checkpoint, step.name, log)

    return RunResult(True, checkpoint, None, log)
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| LangGraph checkpointers | Persist graph state per step; resume and time-travel |
| Temporal | Durable execution with deterministic replay; wrap LLM steps as activities |
| Inngest, Restate, DBOS | Durable step functions with retries |

## Related Patterns

- [Loop Termination](loop-termination.md) applies when the workflow is a loop rather than a fixed sequence.
- [No-Progress Detection](no-progress-detection.md): a step that keeps returning the same invalid output should be rolled back and given a different strategy.
- [Maker–Verifier Split](maker-verifier-split.md) is the strongest kind of step validator.
- [Circuit Breaker for LLMs](../reliability/circuit-breaker.md) handles provider failures underneath. This pattern handles workflow-level failures above them.

## Further Reading

- [LangGraph persistence and checkpointers](https://langchain-ai.github.io/langgraph/concepts/persistence/)
- [Temporal: workflows](https://docs.temporal.io/workflows)
- [Sagas](https://www.cs.cornell.edu/andru/cs711/2002fa/reading/sagas.pdf), Garcia-Molina and Salem, 1987. Compensating actions for long-running transactions.
