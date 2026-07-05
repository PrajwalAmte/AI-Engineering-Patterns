---
title: Reflexion Loop
pillar: loop-engineering
status: emerging
tags: [loops, agents, self-correction, memory, reflection]
related:
  - LLM-as-Judge
  - Loop Termination
  - Maker–Verifier Split
  - No-Progress Detection
contributors: ["@PrajwalAmte"]
last_updated: "2026-07"
description: A three-role loop — Actor, Evaluator, Self-Reflection — where verbal lessons from failed attempts are written to episodic memory and read back on the next try.
sidebar:
  order: 2
---

## What It Is

The Reflexion Loop pattern structures self-correction around three distinct roles rather than one model repeatedly re-answering the same prompt: an **Actor** that attempts the task, an **Evaluator** that scores the attempt, and a **Self-Reflection** step that converts a failure into a short verbal lesson, written to an episodic memory buffer that the Actor reads before its next attempt. The loop repeats until the Evaluator passes the attempt or a termination condition (see the [Loop Termination](/AI-Engineering-Patterns/patterns/loop-engineering/loop-termination/) pattern) is met.

## The Problem It Solves

Naively re-prompting a model with "try again" after a failure rarely produces a materially different attempt — the model has no structured record of *what specifically* went wrong last time, so it tends to repeat the same mistake with cosmetic variation. This shows up as:

- A coding agent re-generating a patch that fails the same test three times in a row, because nothing in its context distinguishes attempt 3 from attempt 1.
- A research agent re-running a failed query with slightly different wording instead of addressing the actual reason the previous result was insufficient.
- Wasted iteration budget: every retry costs the same as the first attempt, with no compounding benefit from having already failed once.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Actor attempts task"] --> B["Evaluator scores the attempt"]
    B --> C{"Passed?"}
    C -->|"Yes"| D["Terminate: success, return output"]
    C -->|"No"| E["Self-Reflection step"]
    E --> F["Write verbal lesson to episodic memory"]
    F --> G{"Termination condition met? (see Loop Termination Pattern)"}
    G -->|"Yes"| H["Terminate: exhausted, return best attempt + lessons"]
    G -->|"No"| I["Actor re-attempts, reading memory buffer"]
    I --> A
</pre>

1. **Separate the three roles explicitly**, even if all three are the same underlying model called with different prompts. Mixing them into a single "critique yourself" prompt collapses the distinction that makes this pattern work.
2. **Actor attempts the task** using the current prompt, tools, and whatever is in the episodic memory buffer from prior attempts.
3. **Evaluator scores the attempt** against an explicit, checkable criterion — ideally an external verifier (tests, schema validation, a rubric) rather than the Actor grading its own work. See the [Maker–Verifier Split](/AI-Engineering-Patterns/patterns/loop-engineering/maker-verifier-split/) pattern for why this separation matters.
4. **On failure, the Self-Reflection step writes a short, specific, verbal lesson** — not a full transcript replay, but a distilled statement of what went wrong and what to try differently ("the patch failed because the import path assumed a flat module layout; the project uses a src/ layout").
5. **The lesson is appended to an episodic memory buffer**, which the Actor reads on its next attempt alongside the original task. The buffer accumulates across attempts within a run, so attempt 4 has the accumulated lessons of attempts 1–3.
6. **The loop terminates** via the same signals as any other agent loop — a passing evaluation, an iteration ceiling, or a no-progress signal — since Reflexion loops can themselves stall if the lessons aren't actually actionable.

## When to Use It

- Tasks with a cheap, reliable automated verifier: code generation with a test suite, structured data extraction with schema validation, agent tool-calling with a checkable success condition.
- Multi-attempt tasks where the *reason* for failure is specific and expressible in language (a wrong assumption, a missed constraint) rather than open-ended quality judgment.
- Situations where retry cost is acceptable (2-4x a single attempt) in exchange for meaningfully higher success rate on attempt 2+.

## When NOT to Use It

- Tasks without a reliable, independent evaluator — if the Evaluator is the same model with the same blind spots as the Actor, failures can go undetected and the loop terminates on a false pass. This is the single most common way this pattern fails silently.
- Latency-critical, real-time responses — the sequential Actor → Evaluator → Self-Reflection → Actor round trip adds meaningful latency that a single-pass response doesn't have.
- Open-ended creative tasks with no checkable success criterion (there is no test suite for "is this poem good") — a rubric-graded Evaluator here just becomes a matter of opinion dressed up as verification.

## Trade-offs

1. **Cost multiplies** — each failed attempt costs an Actor call, an Evaluator call, and a Self-Reflection call; a task needing 3 attempts costs roughly 3x a single-pass approach, sometimes more.
2. **Evaluator quality is the ceiling on the whole pattern** — a weak or biased Evaluator makes every other part of the loop worthless, since the Actor will happily converge on whatever the Evaluator rewards, not what's actually correct.
3. **Verbal lessons can be wrong or overfit** — the Self-Reflection step can misattribute the cause of failure, and the Actor then "corrects" for the wrong reason, sometimes making the next attempt worse.
4. **Memory buffer growth** — across many attempts, the accumulated lessons can grow large enough to compete for context budget with the task itself; this pattern needs to be paired with the [Token Budget Pattern](/AI-Engineering-Patterns/patterns/cost-and-efficiency/token-budget/) in long-running loops.

## Failure Modes

### Rubber-Stamp Evaluation
**Trigger**: The Evaluator is the same model instance (or same model with the same prompt style) as the Actor, effectively grading its own homework.
**Symptom**: The loop terminates with a "pass" on outputs that an independent check would fail, because the Evaluator shares the Actor's blind spots.
**Mitigation**: Use an independent verifier where possible (test execution, schema validators, a different model or a human) rather than a same-model self-critique. See the [Maker–Verifier Split](/AI-Engineering-Patterns/patterns/loop-engineering/maker-verifier-split/) pattern.

### Misattributed Lesson
**Trigger**: The Self-Reflection step identifies a plausible-sounding but incorrect cause for the failure.
**Symptom**: Subsequent attempts "fix" the wrong thing, and the loop either stalls (no measurable improvement) or actively regresses.
**Mitigation**: Ground the Self-Reflection step in concrete evaluator output (the actual failing test's error message, the actual schema validation error) rather than asking the model to freely speculate about why it failed.

### Memory Buffer Bloat
**Trigger**: Long-running loops accumulate many verbal lessons without pruning, and the buffer grows to consume a large fraction of the available context.
**Symptom**: Later attempts have less room for the actual task context, and quality degrades even as the lesson buffer grows.
**Mitigation**: Cap the buffer to the most recent and most relevant N lessons, or periodically summarize the buffer down to its essential, non-redundant points.

## Implementation Example

```python
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class EvalResult:
    passed: bool
    detail: str  # concrete failure detail, e.g. test error message


@dataclass
class ReflexionState:
    task: str
    memory: list = field(default_factory=list)  # verbal lessons
    last_output: object = None


def reflexion_loop(
    task: str,
    actor_fn: Callable[[str, list], object],
    evaluator_fn: Callable[[object], EvalResult],
    reflect_fn: Callable[[object, str], str],
    max_attempts: int = 4,
) -> ReflexionState:
    state = ReflexionState(task=task)

    for attempt in range(1, max_attempts + 1):
        output = actor_fn(task, state.memory)
        state.last_output = output

        result = evaluator_fn(output)
        if result.passed:
            return state  # success — state.last_output is the answer

        # Grounded in the evaluator's concrete failure detail,
        # not free speculation
        lesson = reflect_fn(output, result.detail)
        state.memory.append(lesson)

    return state  # exhausted — caller checks state.last_output + memory
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| Reflexion (research implementation) | Open-source (paper release) | Reference implementation of the Actor/Evaluator/Self-Reflection loop with episodic memory |
| LangGraph | Framework | Explicit multi-node graphs suited to modeling separate Actor/Evaluator/Reflection roles |
| DeepEval / RAGAS | Evaluation libraries | Can serve as the Evaluator role when the task has RAG- or generation-quality dimensions |
| Test runners (pytest, jest, etc.) | General tooling | The most reliable Evaluator for code-generation Reflexion loops |

## Related Patterns

- **[LLM-as-Judge](/AI-Engineering-Patterns/patterns/observability-and-evaluation/llm-as-judge/)** — an offline evaluation harness; this pattern's Evaluator role can use LLM-as-Judge techniques, but Reflexion applies them inside a live retry loop rather than in batch evaluation.
- **[Loop Termination](/AI-Engineering-Patterns/patterns/loop-engineering/loop-termination/)** — supplies the stopping logic this pattern needs to avoid looping indefinitely on an unsolvable task.
- **[Maker–Verifier Split](/AI-Engineering-Patterns/patterns/loop-engineering/maker-verifier-split/)** — the structural principle behind keeping the Evaluator independent of the Actor.
- **[No-Progress Detection](/AI-Engineering-Patterns/patterns/loop-engineering/no-progress-detection/)** — detects when successive Reflexion attempts stop improving, independent of hitting the attempt ceiling.

## Further Reading

- [Reflexion: Language Agents with Verbal Reinforcement Learning (Shinn et al., 2023)](https://arxiv.org/abs/2303.11366)
- [ReAct: Synergizing Reasoning and Acting in Language Models (Yao et al., 2022)](https://arxiv.org/abs/2210.03629)
- [What Is Loop Engineering? A Complete Guide from Prompt to Harness Engineering — Tosea.ai](https://tosea.ai/blog/loop-engineering-ai-agents-complete-guide-2026)