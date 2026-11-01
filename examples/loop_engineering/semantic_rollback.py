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
