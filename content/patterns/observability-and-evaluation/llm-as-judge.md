---
title: LLM-as-Judge
pillar: observability-and-evaluation
status: validated-in-production
tags: [evaluation, llm-judge, quality, testing]
related:
  - Prompt Mutation Testing
  - Shadow Model Evaluation
  - Grounding Verifier
  - Span-Level Tracing
example: examples/observability_and_evaluation/llm_as_judge.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Use a model to grade outputs against a concrete rubric. Run comparisons in both orders and check the judge against human labels before trusting its scores.
sidebar:
  order: 2
---

## What It Is

A judge model reads a question, an answer and a rubric, and returns a score with a short justification. Or it reads two answers and picks the better one. It's how most teams evaluate open-ended output at a scale humans can't cover: regression suites before each deploy, and sampled scoring of live traffic.

The pattern is easy to build and easy to fool yourself with. Most of this page is about the second part.

## The Problem It Solves

Quality regresses quietly. A prompt tweak, a model upgrade or a retrieval change makes answers slightly worse, and nothing throws an error. Exact-match tests can't grade "was this helpful and correct?". Humans can, but not for 500 cases on every pull request, or for 1% of daily traffic.

A judge sits between those options. It's not as reliable as a careful human, but it's consistent, fast and cheap enough to run all the time, as long as you've measured *how* unreliable it is.

## How It Works

<pre class="mermaid">
flowchart TD
    H["~100 human-labelled examples"] --> C{"Judge agrees with<br/>humans often enough?"}
    C -->|"no"| RB["Fix rubric / change judge"]
    RB --> C
    C -->|"yes"| U["Use judge"]
    U --> S["Pointwise: rubric score 1–4"]
    U --> P["Pairwise: A vs B,<br/>asked in both orders"]
    S & P --> A["Aggregate per release / per day"]
    A --> G{"Regression?"}
    G -->|"yes"| B["Block deploy or alert"]
</pre>

1. **Write a rubric with concrete levels.** "4 = right, complete and concise" works better than "rate helpfulness 1–10". Tell the judge outright that length and confidence are not quality.
2. **Ask for a short justification first, then the score,** as structured output. Treat an unparseable verdict as missing data, never as a default score.
3. **Run pairwise comparisons in both orders.** Judges tend to favour whichever answer they read first. If the verdict flips when you swap the order, record a tie.
4. **Calibrate against humans.** Label about 100 examples yourself and measure exact and within-one agreement. Repeat whenever you change the judge model or the rubric.
5. **Track the aggregate, not single scores.** One judge score is noisy. The mean over a few hundred cases is a usable signal.

## When to Use It

- Open-ended outputs (answers, summaries, explanations) where exact match doesn't apply.
- Pre-deploy regression checks on prompts and models.
- Sampled monitoring of production quality between human reviews.

## When NOT to Use It

- **The check can be done in code.** JSON validity, "contains the order ID", "compiles", "matches the reference exactly": write a test. It's cheaper and it's right every time.
- **The judge is weaker than the model being judged.** A small model grading a frontier model's reasoning mostly measures its own limits.
- **Decisions that need accountability.** Compliance sign-off, medical review and individual performance evaluation need a human. The judge can triage, but it can't sign off.

## Trade-offs

- **Known biases.** Judges favour the first answer, longer answers, and answers in their own style, sometimes from their own model family. Swapping orders, length-neutral rubrics and a judge from a different family all help, and none of them remove the bias entirely.
- **Cost.** A judge prompt holds the question, the answer, the rubric and maybe a reference, so it's often longer than the original call. Sample production traffic. Don't judge all of it.
- **Rubric work never ends.** Your first rubric will give everything a 4. Expect several rounds against known-bad examples.

## Failure Modes

**Score inflation.** Every response scores 3 or 4, so the metric can't separate a good release from a bad one. Include known-bad answers in the calibration set. If the judge rates them 3, the rubric is too vague.

**Judging the wrong thing.** The judge rewards confident, polished, well-formatted answers that are wrong. Give it a reference answer or the source documents for factual questions. For pure grounding, use a dedicated [Grounding Verifier](../retrieval-and-memory/grounding-verifier.md).

**Silent judge drift.** The judge model is upgraded behind an alias and scores shift by half a point. The dashboard calls it a quality change. Pin the judge model version, and re-run calibration whenever you change it.

## Implementation Example

Pointwise scoring with a concrete rubric and strict parsing, pairwise comparison in both orders where disagreement becomes a tie, and an agreement check against human labels. The tests include a judge that always picks "A", which this setup correctly reports as a tie.

```bash
cd examples && pytest observability_and_evaluation/test_llm_as_judge.py
```

<!-- example: examples/observability_and_evaluation/llm_as_judge.py -->
```python
"""LLM-as-Judge.

A judge model scores outputs against a rubric whose levels are described
concretely. Two habits make the scores worth trusting: pairwise comparisons
are run in both orders (judges favour whichever answer they read first), and
the judge is checked against human labels before anyone believes its numbers.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

Judge = Callable[[str], str]

RUBRIC = """Score the RESPONSE to the QUESTION for correctness and helpfulness.
1 = wrong or harmful. 2 = partly right but misleading or missing the key point.
3 = right but incomplete or padded. 4 = right, complete and concise.
Judge substance only; length and confidence are not quality.
Reply with JSON: {"reasoning": "<one or two sentences>", "score": 1|2|3|4}"""

PAIRWISE = """Which response answers the QUESTION better? Judge substance, not length.
Reply with JSON: {"reasoning": "<one sentence>", "winner": "A"|"B"|"tie"}"""


def _parse(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    return json.loads(raw[start : end + 1])


def score(judge: Judge, question: str, response: str, reference: str | None = None) -> int | None:
    prompt = f"{RUBRIC}\n\nQUESTION:\n{question}\n\nRESPONSE:\n{response}"
    if reference:
        prompt += f"\n\nREFERENCE ANSWER (for checking facts):\n{reference}"
    try:
        value = int(_parse(judge(prompt))["score"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None  # count unparseable verdicts separately; don't guess
    return value if 1 <= value <= 4 else None


def compare(judge: Judge, question: str, a: str, b: str) -> str:
    """Returns "A", "B" or "tie". Runs both orders; disagreement means tie."""

    def ask(first: str, second: str) -> str:
        raw = judge(f"{PAIRWISE}\n\nQUESTION:\n{question}\n\nRESPONSE A:\n{first}\n\nRESPONSE B:\n{second}")
        try:
            return _parse(raw)["winner"]
        except (KeyError, json.JSONDecodeError):
            return "tie"

    forward = ask(a, b)
    backward = {"A": "B", "B": "A"}.get(ask(b, a), "tie")  # map back to original labels
    return forward if forward == backward else "tie"


@dataclass
class Agreement:
    exact: float  # judge == human
    within_one: float  # |judge - human| <= 1
    unparseable: int


def agreement_with_humans(judge: Judge, labelled: list[tuple[str, str, int]]) -> Agreement:
    """Run this before trusting the judge, and again whenever you change judge model or rubric."""
    exact = near = bad = 0
    for question, response, human in labelled:
        s = score(judge, question, response)
        if s is None:
            bad += 1
            continue
        exact += s == human
        near += abs(s - human) <= 1
    n = len(labelled) or 1
    return Agreement(exact / n, near / n, bad)
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| OpenAI Evals, Inspect (UK AISI), promptfoo | Eval harnesses with model-graded scorers |
| Braintrust, LangSmith, Langfuse | Datasets, judge scorers and experiment tracking |
| DeepEval, Ragas | Libraries of pre-built judge metrics (G-Eval, faithfulness, …) |

## Related Patterns

- [Prompt Mutation Testing](prompt-mutation-testing.md) uses judges to check that variants of a prompt stay robust.
- [Shadow Model Evaluation](shadow-model-evaluation.md) uses pairwise judging to compare a candidate model against production.
- [Grounding Verifier](../retrieval-and-memory/grounding-verifier.md) is a narrow judge for one property, and more reliable for that reason.
- [Span-Level Tracing](span-level-tracing.md): attach scores to traces so a low score links to its trace.

## Further Reading

- [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685), Zheng et al., 2023. Documents position, verbosity and self-preference bias.
- [Who Validates the Validators?](https://arxiv.org/abs/2404.12272), Shankar et al., 2024. On aligning judges with human preferences.
- [Creating a LLM-as-a-Judge That Drives Business Results](https://hamel.dev/blog/posts/llm-judge/), Hamel Husain
