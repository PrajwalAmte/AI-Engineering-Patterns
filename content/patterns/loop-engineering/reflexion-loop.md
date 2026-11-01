---
title: Reflexion Loop
pillar: loop-engineering
status: emerging
tags: [agents, self-correction, memory, loops]
related:
  - Maker–Verifier Split
  - No-Progress Detection
  - Loop Termination
  - Graph of Thoughts
example: examples/loop_engineering/reflexion_loop.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Actor attempts, evaluator checks, and on failure a reflection step writes one specific lesson to a small memory that the next attempt reads. A repeated lesson means stop.
sidebar:
  order: 4
---

## What It Is

Reflexion (Shinn et al., 2023) separates self-correction into three roles:

- **Actor**: attempts the task, reading any lessons in memory.
- **Evaluator**: checks the attempt. Ideally this is a test run, not an opinion.
- **Reflection**: on failure, writes *one short, specific lesson* ("using abs() broke negative inputs; return a + b directly").

Lessons accumulate in a small episodic memory for the rest of the run. Each new attempt starts from the task plus what previous attempts learned.

## The Problem It Solves

"Try again" without structure gives near-identical retries. The model has no record of *what* went wrong, so attempt three fails the same test as attempt one with different variable names. Each retry costs as much as the first and teaches nothing.

Giving it the full transcript of failures is too much. It wastes context, and the model fixates on details. A distilled lesson is the useful middle ground.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Actor: attempt (task + lessons)"] --> E["Evaluator: run tests / validate"]
    E -->|"pass"| D["Done"]
    E -->|"fail + feedback"| R["Reflection: one specific lesson"]
    R --> M{"Lesson already in memory?"}
    M -->|"yes"| S["Stop: not learning"]
    M -->|"no"| W["Add to memory (bounded)"]
    W --> C{"Trials left?"}
    C -->|"yes"| A
    C -->|"no"| X["Stop: return best attempt + lessons"]
</pre>

1. **Keep the three roles as separate calls,** even with the same model. A single "critique yourself and retry" prompt merges them, and the pattern loses its value.
2. **Give the evaluator real feedback to pass on:** test output, validation errors, the exact failing case.
3. **Force reflections to be one specific sentence** about the mistake and the change to make. Generic lessons ("be more careful") don't help.
4. **Bound and de-duplicate memory.** Keep the last few lessons. If a new lesson matches an old one, the loop isn't learning, so stop.
5. **Stop on pass, on trials exhausted, or on a repeated lesson.** Return the best attempt and the lessons, which are useful to a human picking up the task.

## When to Use It

- Tasks with a reliable evaluator that gives informative feedback: code with tests, extraction with validators, puzzles with checkers.
- First attempts often fail for fixable, explainable reasons.

## When NOT to Use It

- **No evaluator.** A reflection with nothing to reflect on produces made-up lessons.
- **The failure is missing knowledge,** not a mistake. Reflection can't supply facts. Retrieval or tools can.
- **Latency-sensitive paths.** Each trial is at least two calls.

## Trade-offs

- **Calls per trial:** actor plus reflection, plus the evaluator if it's a model.
- **Lessons can mislead.** A wrong diagnosis ("the bug is in parsing" when it's in the math) sends the next attempt in the wrong direction. Good evaluator feedback is the main defense.
- **Memory scope.** Lessons are scoped to one run here. Carrying them across runs is powerful and risky: a lesson from one context can be wrong in another.

## Failure Modes

**Lesson oscillation.** "Use approach A" is followed by "use approach B", then "use approach A" again. De-duplication catches exact repeats. [No-Progress Detection](no-progress-detection.md) on the attempts catches the rest.

**The actor grades itself.** The evaluator is a prompt asking the actor whether it did well, and it says yes. Use an external check ([Maker–Verifier Split](maker-verifier-split.md)).

**Unbounded memory.** Twenty lessons, half of them outdated, crowd the prompt. Keep the last few.

## Implementation Example

Actor, evaluator and reflector as separate callables, bounded and de-duplicated memory, and stop reasons for pass, exhausted trials and repeated lessons. In the test, the evaluator actually runs the generated function against cases, and the second attempt passes because of the first attempt's lesson.

```bash
cd examples && pytest loop_engineering/test_reflexion_loop.py
```

<!-- example: examples/loop_engineering/reflexion_loop.py -->
```python
"""Reflexion Loop.

Three roles, three calls: the actor attempts, the evaluator checks (ideally a
test, not an opinion), and on failure a reflection step writes one short,
specific lesson into memory. The next attempt reads the lessons. Memory is
small and de-duplicated: a lesson repeated is a sign the loop is stuck.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

Actor = Callable[[str, list[str]], str]  # (task, lessons) -> attempt
Evaluator = Callable[[str], tuple[bool, str]]  # attempt -> (passed, feedback)
Reflector = Callable[[str, str, str], str]  # (task, attempt, feedback) -> one-sentence lesson


@dataclass
class Memory:
    max_lessons: int = 5
    lessons: list[str] = field(default_factory=list)

    def add(self, lesson: str) -> bool:
        """Returns False if this lesson was already learned (a stall signal)."""
        key = lesson.strip().lower()
        if any(key == old.strip().lower() for old in self.lessons):
            return False
        self.lessons.append(lesson.strip())
        self.lessons = self.lessons[-self.max_lessons :]  # recent lessons matter most
        return True


@dataclass
class Result:
    passed: bool
    attempt: str
    trials: int
    lessons: list[str]
    stop_reason: str


def reflexion(
    task: str, actor: Actor, evaluate: Evaluator, reflect: Reflector, max_trials: int = 4, memory: Memory | None = None
) -> Result:
    memory = memory or Memory()
    attempt = ""
    for trial in range(1, max_trials + 1):
        attempt = actor(task, list(memory.lessons))
        passed, feedback = evaluate(attempt)
        if passed:
            return Result(True, attempt, trial, memory.lessons, "passed")
        lesson = reflect(task, attempt, feedback)
        if not memory.add(lesson):
            return Result(False, attempt, trial, memory.lessons, "repeated lesson: not learning")
    return Result(False, attempt, max_trials, memory.lessons, "out of trials")


REFLECT_PROMPT = """Task: {task}
Your attempt: {attempt}
What went wrong: {feedback}
In ONE sentence, state the specific mistake and what to do differently next time.
Don't restate the task. Don't apologise."""
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| noahshinn/reflexion | Reference implementation from the paper |
| LangGraph | Reflection and Reflexion agent templates |
| DSPy | Optimizes prompts from feedback, a related approach at the program level |

## Related Patterns

- [Maker–Verifier Split](maker-verifier-split.md) provides the independent evaluator.
- [No-Progress Detection](no-progress-detection.md) catches stalls that de-duplication misses.
- [Loop Termination](loop-termination.md) supplies the outer stop rules.
- [Graph of Thoughts](../graph-patterns/graph-of-thoughts.md) combines many attempts instead of improving one.

## Further Reading

- [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366), Shinn et al., 2023
- [Self-Refine: Iterative Refinement with Self-Feedback](https://arxiv.org/abs/2303.17651), Madaan et al., 2023
- [Large Language Models Cannot Self-Correct Reasoning Yet](https://arxiv.org/abs/2310.01798), Huang et al., 2023. Why the evaluator must be external.
