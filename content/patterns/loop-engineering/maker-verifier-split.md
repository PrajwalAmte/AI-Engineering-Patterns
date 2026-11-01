---
title: Maker–Verifier Split
pillar: loop-engineering
status: emerging
tags: [agents, verification, loops, quality]
related:
  - Loop Termination
  - Reflexion Loop
  - LLM-as-Judge
  - Human-in-the-Loop
example: examples/loop_engineering/maker_verifier_split.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: The agent that does the work never decides it's done. An independent verifier checks only the output against the task's criteria and sends back concrete issues.
sidebar:
  order: 3
---

## What It Is

Two roles that are never the same call:

- **Maker**: produces the work and revises it using the issues it's given.
- **Verifier**: checks the *output* against acceptance criteria taken from the task, not from what the maker tends to produce. It returns pass, or a list of concrete issues.

The verifier never sees the maker's reasoning. If repeated rejections pile up, or the verifier can't decide, a human gets the case.

## The Problem It Solves

When the same agent produces and approves its work, it approves its own blind spots. A coding agent that misread the spec writes a patch and then "reviews" it with the same misreading. A research agent stops when *it* feels confident, which isn't the same as the research being sufficient. Studies of self-correction find models often can't fix their own reasoning errors without an external signal.

From the outside, an agent's "done" can't be checked unless something independent checks it.

## How It Works

<pre class="mermaid">
sequenceDiagram
    participant M as Maker
    participant V as Verifier (sees output only)
    participant H as Human
    M->>V: output
    alt passes criteria
        V-->>M: verified
    else concrete issues
        V-->>M: ["age must be an integer", ...]
        M->>V: revised output
    else can't decide, or N rejections
        V->>H: escalate with history
    end
</pre>

1. **Write the acceptance criteria first,** from the task spec. A verifier built by looking at the maker's outputs just learns to accept the maker's habits.
2. **Prefer mechanical verifiers:** tests, schema validation, linters, type checkers. They can't be persuaded.
3. **When the verifier is a model,** give it a different prompt and ideally a different model, and pass it only the output and the criteria. Never the maker's explanation, which is effectively an argument for approval.
4. **Return issues, not scores.** "age must be a non-negative integer" is something the maker can act on. "6/10" isn't.
5. **Escalate on repeated failure or uncertainty.** Don't let a maker and a verifier argue indefinitely.

## When to Use It

- Unattended loops that end with a claim of "done": coding agents, data extraction, report generation.
- Outputs with checkable criteria (tests, schemas, rubrics).
- Workflows where a wrong "done" is expensive.

## When NOT to Use It

- **No independent criteria exist.** A verifier that's just a second opinion from the same model doubles cost and adds little. Get a real check, or a human.
- **Trivial outputs** where the maker's output is already checked downstream.

## Trade-offs

- **More calls and more latency** per task, especially with model-based verifiers.
- **Criteria take work to write.** That work is the real value of this pattern. It forces "done" to be defined.
- **Overly strict verifiers** reject acceptable work and push loops into escalation. Review a sample of rejections.

## Failure Modes

**The verifier reads the maker's justification.** "I've verified this handles all edge cases" persuades a model-based verifier to approve. Structurally strip everything but the output, as the example does by construction.

**Vague rejections.** The verifier says "not good enough" and the maker changes something arbitrary. Require specific, actionable issues.

**Shared blind spots.** The same model family as maker and verifier misses the same class of error. Mix in mechanical checks, or use a different model family for verification.

## Implementation Example

A maker/verifier loop where the verifier receives only the output and the criteria, issues flow back to the maker, and uncertainty or repeated rejection escalates. It includes a helper for building mechanical verifiers from small check functions. The tests confirm the verifier never sees the maker's rationale.

```bash
cd examples && pytest loop_engineering/test_maker_verifier_split.py
```

<!-- example: examples/loop_engineering/maker_verifier_split.py -->
```python
"""Maker-Verifier Split.

The agent that does the work never decides it's done. A separate verifier
checks the output against the task's own acceptance criteria, sees only the
output (never the maker's reasoning, which would talk it into agreeing), and
returns concrete issues the maker can act on. Repeated rejection, or a
verifier that can't decide, goes to a human.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Attempt:
    output: str
    rationale: str = ""  # maker's explanation: logged, never shown to the verifier


@dataclass
class Verdict:
    passed: bool
    issues: list[str] = field(default_factory=list)
    uncertain: bool = False


Maker = Callable[[str, list[str]], Attempt]  # (task, issues from last rejection) -> attempt
Verifier = Callable[[str, str], Verdict]  # (acceptance criteria, output) -> verdict


@dataclass
class Result:
    status: str  # "verified" | "escalated"
    output: str
    rounds: int
    history: list[tuple[str, Verdict]] = field(default_factory=list)


def run(task: str, criteria: str, maker: Maker, verifier: Verifier, max_rounds: int = 3) -> Result:
    issues: list[str] = []
    history: list[tuple[str, Verdict]] = []
    for round_no in range(1, max_rounds + 1):
        attempt = maker(task, issues)
        verdict = verifier(criteria, attempt.output)  # output only, by construction
        history.append((attempt.output, verdict))
        if verdict.uncertain:
            return Result("escalated", attempt.output, round_no, history)
        if verdict.passed:
            return Result("verified", attempt.output, round_no, history)
        issues = verdict.issues or ["verifier rejected the output without details"]
    return Result("escalated", history[-1][0], max_rounds, history)


def all_of(*checks: Callable[[str], str | None]) -> Callable[[str, str], Verdict]:
    """Build a mechanical verifier from checks that return an issue string or None.
    Mechanical checks (tests, schemas, linters) can't be persuaded; prefer them."""

    def verify(criteria: str, output: str) -> Verdict:
        issues = [msg for check in checks if (msg := check(output))]
        return Verdict(not issues, issues)

    return verify
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| pytest, type checkers, linters | Mechanical verifiers for code |
| JSON Schema / Pydantic | Mechanical verifiers for structured output |
| LLM judge with a separate model | When criteria are semantic; see LLM-as-Judge |

## Related Patterns

- [Loop Termination](loop-termination.md): the verifier *is* the goal check.
- [Reflexion Loop](reflexion-loop.md) turns verifier issues into lessons for the next attempt.
- [LLM-as-Judge](../observability-and-evaluation/llm-as-judge.md) covers the pitfalls of model-based verifiers.
- [Human-in-the-Loop](../governance/human-in-the-loop.md) is where escalations go.

## Further Reading

- [Large Language Models Cannot Self-Correct Reasoning Yet](https://arxiv.org/abs/2310.01798), Huang et al., 2023
- [Let's Verify Step by Step](https://arxiv.org/abs/2305.20050), Lightman et al. (OpenAI), 2023. On separate verifiers.
- [Reflexion](https://arxiv.org/abs/2303.11366), Shinn et al., 2023
