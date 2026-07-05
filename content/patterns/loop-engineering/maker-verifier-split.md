---
title: Maker–Verifier Split
pillar: loop-engineering
status: emerging
tags: [loops, agents, verification, human-in-the-loop, control-flow]
related:
  - Reflexion Loop
  - LLM-as-Judge
  - Loop Termination
  - Tool Output Firewall
contributors: ["@PrajwalAmte"]
last_updated: "2026-07"
description: Structurally separate the agent that does the work from the agent or process that certifies it's done, so "done" is an independent claim rather than the maker grading its own homework.
sidebar:
  order: 4
---

## What It Is

The Maker–Verifier Split pattern structurally separates the agent producing work (the Maker) from the process that certifies the work is actually complete and correct (the Verifier). The two run as independent sub-agents, processes, or checks — never the same call, and ideally not even the same model configuration — so that a loop's "it is done" signal means something more than the Maker's own self-assessment.

## The Problem It Solves

An unattended agent loop is also, by definition, an agent making mistakes unattended. If the same agent that produces an output is also the one deciding whether that output is good enough, the loop inherits every blind spot the Maker has: it will tend to approve outputs that satisfy its own (possibly wrong) understanding of the task, because it has no external check against that understanding. Concretely:

- A coding agent that "reviews its own diff" tends to approve patches that reflect its own misreading of the spec, since the same misreading produced both the patch and the review.
- A research agent that decides for itself when it has "gathered enough sources" tends to stop exactly when its own uncertainty happens to be low, which is not the same as when the research is actually sufficient.
- Without an independent verifier, a long-running loop's claim of "done" is unfalsifiable from inside the system — the only way to catch a wrong "done" is for a human to check the output after the fact, which defeats much of the point of running the loop unattended.

## How It Works

<pre class="mermaid">
sequenceDiagram
    participant M as Maker
    participant V as Verifier
    participant H as Human (escalation path)

    M->>M: Produce attempt
    M->>V: Submit output for verification
    V->>V: Check against independent criteria (tests, schema, rubric, or separate model)
    alt Verifier passes
        V-->>M: Approved
        M->>M: Terminate loop: success
    else Verifier fails
        V-->>M: Rejected + concrete reason
        M->>M: Re-attempt using rejection reason
    end
    Note over M,V: If rejected N times or Verifier itself is uncertain
    V->>H: Escalate for human judgment
    H-->>M: Final decision
</pre>

1. **Define the Verifier before building the Maker's loop.** The Verifier's criteria should come from the task specification, not be reverse-engineered from what the Maker tends to produce — otherwise the Verifier ends up validating the Maker's habits rather than the actual requirement.
2. **Keep the Verifier's inputs independent of the Maker's reasoning.** The Verifier should check the *output* (does the code pass tests, does the data match the schema, does the answer satisfy the rubric) without access to the Maker's internal justification for why it believes the output is correct — access to that justification is exactly what lets a Verifier get talked into approving a flawed output.
3. **Prefer mechanical verifiers over model-based ones where possible.** A test suite, a schema validator, or a static analyzer cannot be persuaded; a second LLM call judging the first LLM's work can be, especially if both share training data, instruction-following habits, or blind spots.
4. **When a model-based Verifier is unavoidable**, use a genuinely different model, prompt, or vantage point than the Maker — grading the Maker's own reasoning trace with the Maker's own voice reproduces the self-certification problem this pattern exists to avoid.
5. **Give rejections a concrete, actionable reason**, not just pass/fail — this is what the Maker's next attempt (or a [Reflexion Loop](/AI-Engineering-Patterns/patterns/loop-engineering/reflexion-loop/)) uses to actually improve rather than re-guessing.
6. **Wire an escalation path for Verifier uncertainty**, not just Maker failure. A Verifier that itself can't confidently pass or fail an attempt after repeated tries should hand off to a human rather than defaulting to either approval or endless rejection.

## When to Use It

- Autonomous or semi-autonomous loops running with limited human supervision, where a wrong "done" signal has real cost (shipped code, sent communications, executed transactions).
- Tasks where an independent, mechanical check exists or can be built (tests, schema validation, static analysis, a business-rule engine).
- Any loop pattern (Reflexion Loop, plan-execute-verify) that already needs an evaluator or goal check — this pattern is the design principle for how to make that check trustworthy.

## When NOT to Use It

- Low-stakes, easily-reversible tasks where a wrong "done" costs little and a human reviews the output anyway before it matters — the added architectural complexity isn't earning its cost.
- Tasks with no meaningful way to construct an independent verifier (deeply subjective creative work with no rubric) — forcing a Maker–Verifier split here just relocates the subjectivity into the Verifier's opinion, dressed up as independent verification.
- Extremely tight latency budgets where the two-hop Maker → Verifier round trip (and any escalation path) doesn't fit the SLA, and the task's stakes genuinely don't justify the added latency.

## Trade-offs

1. **Verifier quality becomes the real bottleneck** — a weak or gameable Verifier gives false confidence; the whole pattern is only as good as the independence and rigor of the check.
2. **Added latency and cost** — every attempt now costs a Maker call plus a Verifier call (and occasionally a human escalation), compared to a single self-assessed pass.
3. **Building a good mechanical Verifier is itself engineering work** — for many real tasks, "does the code pass tests" is easy to define, but "does this research answer sufficiently address the question" is not, and a weak proxy Verifier can be worse than an honest self-assessment.
4. **Escalation paths need real ownership** — an escalation queue that no human actually monitors turns "escalate to human" into a silent dead end, which is worse than the loop failing loudly.

## Failure Modes

### Verifier Shares the Maker's Blind Spot
**Trigger**: The Verifier is a model-based check using the same underlying model, similar prompting style, or the same misreading of the task spec as the Maker.
**Symptom**: The Verifier approves outputs that reflect a shared misunderstanding, giving false confidence that independent verification occurred.
**Mitigation**: Use mechanical checks (tests, schema validation) wherever the task allows; when a model-based Verifier is necessary, deliberately use a different model or a materially different prompt framing than the Maker.

### Verifier Reverse-Engineered from Maker Output
**Trigger**: The Verifier's criteria were written by observing what the Maker tends to produce, rather than derived from the original task specification.
**Symptom**: The Verifier validates the Maker's habitual patterns rather than the actual requirement, and drifts further from the true spec as the Maker's habits evolve.
**Mitigation**: Derive Verifier criteria from the task specification or acceptance criteria directly, and review them independently of any Maker output.

### Silent Escalation Dead End
**Trigger**: An escalation path to a human exists on paper (a queue, a ticket, a Slack channel) but nobody is actually monitoring it.
**Symptom**: Attempts that should have been caught and reviewed instead sit unresolved indefinitely, and the loop either times out with no result or a downstream process treats the unresolved state as a default approval.
**Mitigation**: Treat the escalation path as a monitored on-call responsibility with an SLA, not a fire-and-forget queue; alert on escalation backlog the same way you'd alert on any other production queue.

## Implementation Example

```python
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class VerifyStatus(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"  # triggers human escalation


@dataclass
class VerifyResult:
    status: VerifyStatus
    reason: str


def maker_verifier_loop(
    task: str,
    maker_fn: Callable[[str, list], object],
    verifier_fn: Callable[[object], VerifyResult],
    escalate_fn: Callable[[object, list], object],
    max_attempts: int = 4,
) -> dict:
    rejection_reasons: list = []

    for attempt in range(1, max_attempts + 1):
        output = maker_fn(task, rejection_reasons)
        result = verifier_fn(output)  # independent of maker_fn's reasoning

        if result.status == VerifyStatus.APPROVED:
            return {"output": output, "status": "success", "attempts": attempt}

        if result.status == VerifyStatus.UNCERTAIN:
            human_decision = escalate_fn(output, rejection_reasons)
            return {
                "output": human_decision,
                "status": "human_reviewed",
                "attempts": attempt,
            }

        rejection_reasons.append(result.reason)

    # Exhausted attempts without approval — escalate rather than
    # silently returning an unverified output
    human_decision = escalate_fn(output, rejection_reasons)
    return {"output": human_decision, "status": "escalated_ceiling", "attempts": max_attempts}


# Example mechanical verifier: independent of the maker's reasoning trace
def verifier_fn(output: dict) -> VerifyResult:
    if output.get("tests_passed") is True:
        return VerifyResult(VerifyStatus.APPROVED, "all tests passed")
    if output.get("tests_run", 0) == 0:
        return VerifyResult(VerifyStatus.UNCERTAIN, "no tests were executed")
    return VerifyResult(VerifyStatus.REJECTED, f"failed: {output.get('failure_detail')}")
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| Test runners (pytest, jest, go test) | General tooling | The most common mechanical Verifier for code-generation Makers |
| JSON Schema / Pydantic validators | Open-source | Mechanical Verifier for structured-output Makers |
| Static analyzers / linters | General tooling | Cheap, non-gameable Verifier layer that runs before more expensive checks |
| Human-review queues (Jira, Linear, custom escalation UIs) | General tooling | The escalation path for Verifier-uncertain cases; needs monitored ownership |

## Related Patterns

- **[Reflexion Loop](/AI-Engineering-Patterns/patterns/loop-engineering/reflexion-loop/)** — a loop shape where this pattern's principle (independent Evaluator) is directly applicable; Reflexion without a genuinely independent Evaluator degrades into self-certification.
- **[LLM-as-Judge](/AI-Engineering-Patterns/patterns/observability-and-evaluation/llm-as-judge/)** — can serve as a model-based Verifier, provided it uses a different model or vantage point than the Maker.
- **[Loop Termination](/AI-Engineering-Patterns/patterns/loop-engineering/loop-termination/)** — the Verifier's pass/fail decision is typically one of the goal-check inputs to overall loop termination.
- **[Tool Output Firewall](/AI-Engineering-Patterns/patterns/security-and-trust/tool-output-firewall/)** — a related separation-of-concerns pattern that sanitizes untrusted tool output re-entering context, similar in spirit to keeping the Verifier's inputs independent.

## Further Reading

- [Loop Engineering: The Guide for AI Agents — Lushbinary](https://lushbinary.com/blog/loop-engineering-ai-coding-agents-guide/)
- [GitHub: loop-engineering patterns and CLI tools — cobusgreyling](https://github.com/cobusgreyling/loop-engineering)
- [Reflexion: Language Agents with Verbal Reinforcement Learning (Shinn et al., 2023)](https://arxiv.org/abs/2303.11366)