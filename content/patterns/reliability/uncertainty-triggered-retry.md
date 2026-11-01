---
title: Uncertainty-Triggered Retry
pillar: reliability
status: emerging
tags: [reliability, retry, confidence, structured-output]
related:
  - Model Router
  - LLM-as-Judge
  - Request Hedging for LLMs
  - Grounding Verifier
example: examples/reliability/uncertainty_triggered_retry.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Treat an unsure answer as a soft failure. Retry once with a stronger setup, and if that's unsure too, tell the user instead of guessing.
sidebar:
  order: 3
---

## What It Is

Before serving an answer, score how unsure it looks. If it's above a threshold, retry once with a stronger model or a more careful prompt. If the retry is also unsure, serve it marked as uncertain ("I couldn't confirm this…") rather than presenting a guess as fact.

Retries usually react to errors. This one reacts to answers that came back with a 200 and shouldn't be trusted.

## The Problem It Solves

Some bad answers announce themselves. A small model says "I'm not sure, it might be X", or returns JSON with half the required fields empty, or produces a sentence where every token was a low-probability pick. The API call succeeded, so no error handler fires, and the answer goes straight to the user.

You could send everything to the strongest model, but that's the expensive fix. Most answers from the cheap model are fine, and this pattern pays for the strong model only on the ones that aren't.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Base model answer"] --> S["Uncertainty score:<br/>1. required fields present?<br/>2. mean token logprob<br/>3. hedging phrases"]
    S -->|"below threshold"| OK["Serve"]
    S -->|"above threshold"| R["Retry once: stronger model<br/>+ 'say what's missing'"]
    R --> S2["Score again"]
    S2 -->|"below"| OK2["Serve retry"]
    S2 -->|"above"| U["Serve with an explicit<br/>uncertainty notice"]
</pre>

Signals, from most to least reliable:

1. **Structure.** If you asked for JSON with required fields and got invalid JSON or empty fields, the answer is unusable whatever it says. This signal has almost no false positives.
2. **Token logprobs.** A low mean log-probability across the answer means the model was choosing among many plausible tokens. Not every provider exposes logprobs. When yours does, it's better than any regex.
3. **Hedging language.** "I'm not sure", "possibly", "it's unclear". This is the noisiest signal: careful, correct answers hedge too. Use it as a fallback.

The retry uses a stronger model (see [Model Router](../inference-and-serving/model-router.md)) and a prompt that permits "I don't know" and asks the model to name what's missing. That makes an honest abstention more likely than a confident guess.

## When to Use It

- A cheap model handles most traffic, and you want a safety net for the cases it can't handle.
- Structured extraction, where an incomplete output is useless downstream.
- Users act on answers, so "I'm not sure" is better than wrong.

## When NOT to Use It

- **Creative or exploratory tasks,** where hedging is appropriate and not a defect.
- **You're already on the strongest model** and there's nothing better to retry with. Skip straight to marking the answer as uncertain.
- **Domains where careful answers are the norm** (medical, legal). Hedging language there is often *correct*, so rely on structure and logprobs instead.

## Trade-offs

- **Cost and latency on the uncertain fraction.** Those requests pay for two calls and wait for both. That's fine at 5–10% of traffic and a problem at 40%, which means the base model is the wrong choice.
- **False positives from cautious answers.** Phrase matching flags "this usually works, but may fail if…". Review a sample of retried answers, and tighten the phrase list if retries are mostly unnecessary.
- **Training models out of hedging hides uncertainty.** If you push prompts to "never hedge", the base model will sound confident and be wrong, and this signal goes blind. Let models express doubt, and catch it here.

## Failure Modes

**Retry loops.** The question can't be answered from the available context, so every model hedges and someone adds "retry up to 3 times". Allow one retry. Two unsure answers is itself the answer: tell the user what's missing.

**Unmeasured signals.** The team switches to a provider without logprobs, and the uncertainty rate drops from 8% to 2%. Nothing improved. Track which signals fired, not just the overall rate.

**Overconfident retries.** The stronger model answers confidently and wrongly where the weak one hedged honestly. For high-stakes paths, verify the retry's claims ([Grounding Verifier](../retrieval-and-memory/grounding-verifier.md)) instead of trusting it because it's the bigger model.

## Implementation Example

A scorer that combines structural completeness, logprobs and hedge phrases, one retry with a stronger model and an "admit what's missing" prompt, and an `uncertain` flag the UI can show. The tests cover each signal and confirm there's never a second retry.

```bash
cd examples && pytest reliability/test_uncertainty_triggered_retry.py
```

<!-- example: examples/reliability/uncertainty_triggered_retry.py -->
```python
"""Uncertainty-Triggered Retry.

Treat a low-confidence answer as a soft failure: score it, and if it looks
unsure, retry once with a stronger setup. If the retry is unsure too, say so
to the user instead of retrying forever.

Signals, strongest first: structured output missing required fields; mean
token logprob (when the provider exposes it); hedging language.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass

HEDGES = re.compile(
    r"\b(i'?m not (entirely |completely )?sure|i (think|believe|guess)|possibly|might be|may be|"
    r"it'?s unclear|i cannot (confidently|be certain)|hard to say|not certain)\b",
    re.I,
)


@dataclass
class Completion:
    text: str
    token_logprobs: list[float] | None = None  # None when the provider doesn't expose them


Model = Callable[[str], Completion]


def uncertainty(c: Completion, required_keys: list[str] | None = None) -> float:
    """0.0 = confident, 1.0 = clearly unsure."""
    if required_keys is not None:
        try:
            data = json.loads(c.text)
        except json.JSONDecodeError:
            return 1.0
        if not isinstance(data, dict) or any(data.get(k) in (None, "") for k in required_keys):
            return 1.0

    signals = []
    if c.token_logprobs:
        mean = sum(c.token_logprobs) / len(c.token_logprobs)
        # mean logprob 0 -> confident; -2 or lower -> unsure
        signals.append(min(1.0, max(0.0, -mean / 2)))
    hedges = len(HEDGES.findall(c.text))
    if hedges:
        signals.append(min(1.0, 0.5 * hedges))
    return max(signals, default=0.0)


@dataclass
class Answer:
    text: str
    attempts: int
    uncertain: bool  # true when even the retry was unsure: tell the user


def answer(
    prompt: str,
    base: Model,
    stronger: Model,
    threshold: float = 0.5,
    required_keys: list[str] | None = None,
) -> Answer:
    first = base(prompt)
    if uncertainty(first, required_keys) < threshold:
        return Answer(first.text, 1, False)

    retry_prompt = (
        f"{prompt}\n\nWork through this carefully before answering. "
        "If the information needed is not available, say exactly what is missing."
    )
    second = stronger(retry_prompt)
    unsure = uncertainty(second, required_keys) >= threshold
    # One retry only. Two unsure answers usually mean the question can't be
    # answered from what the model has, and a third call won't change that.
    return Answer(second.text, 2, unsure)


def mean_prob(c: Completion) -> float | None:
    """Handy for dashboards: average token probability, if logprobs are available."""
    if not c.token_logprobs:
        return None
    return sum(math.exp(lp) for lp in c.token_logprobs) / len(c.token_logprobs)
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| OpenAI Chat Completions `logprobs` | Per-token log-probabilities |
| vLLM, llama.cpp, TGI | Logprobs available when you self-host |
| Structured output / JSON schema modes | Make the structural signal reliable |
| Guardrails AI, Instructor | Validation with re-ask loops (cap them at one) |

## Related Patterns

- [Model Router](../inference-and-serving/model-router.md) picks the tier up front. This pattern corrects the choice after the fact.
- [LLM-as-Judge](../observability-and-evaluation/llm-as-judge.md) is a stronger but more expensive uncertainty signal for high-stakes paths.
- [Request Hedging for LLMs](request-hedging.md) handles *slow* answers. This pattern handles *unsure* ones.
- [Grounding Verifier](../retrieval-and-memory/grounding-verifier.md) checks that the retry's confident answer is actually supported.

## Further Reading

- [Teaching Models to Express Their Uncertainty in Words](https://arxiv.org/abs/2205.14334), Lin, Hilton and Evans, 2022
- [Semantic Uncertainty: Linguistic Invariances for Uncertainty Estimation in Natural Language Generation](https://arxiv.org/abs/2302.09664), Kuhn, Gal and Farquhar, 2023
- [Language Models (Mostly) Know What They Know](https://arxiv.org/abs/2207.05221), Kadavath et al. (Anthropic), 2022
