---
title: No-Progress Detection
pillar: loop-engineering
status: emerging
tags: [loops, agents, convergence, oscillation, control-flow]
related:
  - Loop Termination
  - Reflexion Loop
  - Embedding Drift Detector
contributors: ["@PrajwalAmte"]
last_updated: "2026-07"
description: Detect stalled or oscillating agent loops by measuring the delta between successive iterations, so the loop can stop before exhausting its full iteration ceiling.
sidebar:
  order: 3
---

## What It Is

The No-Progress Detection pattern measures how much an agentic loop's state actually changes from one iteration to the next, and stops the loop early when that measurement shows a plateau (no meaningful change) or an oscillation (cycling between a small number of near-identical states) — rather than letting the loop run all the way to its iteration ceiling regardless of whether it's still making progress.

## The Problem It Solves

An iteration ceiling guarantees a loop eventually stops, but it's a blunt instrument: it lets a loop burn its *entire* budget even when it visibly stopped improving several iterations earlier. Two specific failure shapes are common enough to name:

- **Plateau**: the loop keeps producing output, but each successive attempt is functionally the same as the last — a coding agent that keeps "fixing" a bug with the identical patch, a research agent that keeps re-running the same query with cosmetic rewording.
- **Oscillation**: the loop alternates between two (or a small cycle of) near-identical states without ever settling — an agent that alternates between two tool calls, or a Reflexion-style loop where the Self-Reflection step keeps "correcting" the Actor back and forth between two wrong answers.

Both waste the remaining iteration budget and, in production, the added latency and cost of running to the ceiling rather than stopping the moment the stall is detectable.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Iteration completes, output added to history"] --> B["Compute delta vs. recent history"]
    B --> C{"Delta classification"}
    C -->|"Improving"| D["Continue loop"]
    C -->|"Plateaued (delta ~0 for N iterations)"| E["Terminate: stalled"]
    C -->|"Oscillating (repeating cycle detected)"| F["Terminate: stalled"]
    C -->|"Regressing"| G["Continue loop, but flag for review"]
</pre>

1. **Maintain a rolling history** of the loop's output at each iteration — not the full context, just the state being evaluated for progress (a patch diff, a generated answer, a tool-call sequence).
2. **Choose a delta metric appropriate to the task.** Options include exact or near-exact match (cheap, works for plateau detection), edit distance or token-level diff (works for text), embedding cosine similarity (works for semantic drift), or task-specific signals like test-pass count (works best when available, since it measures actual progress rather than surface similarity).
3. **Classify the trend** after each iteration: *improving* (delta shows meaningful forward movement), *plateaued* (delta near zero for a patience window of N consecutive iterations), *oscillating* (the history repeats a short cycle of 2-3 states), or *regressing* (the task-specific signal is getting worse, not just unchanged).
4. **Apply a patience window before terminating on plateau or oscillation** — a single flat iteration is normal; only stop after the delta stays flat, or the cycle repeats, for a configured number of consecutive iterations.
5. **On termination, return the best iteration seen so far**, not necessarily the last one — especially important for oscillating loops, where the last state may not be the best of the cycle.

## When to Use It

- Any bounded loop pattern (Reflexion Loop, iterative refinement, agent re-planning) where a measurable delta between iterations is available and cost or latency savings from stopping early matter.
- Loops that have previously been observed to oscillate or plateau in practice — this pattern is easiest to justify once you've seen the failure mode, harder to pre-emptively tune correctly.
- Systems where a task-specific progress signal already exists (test-pass count, retrieval-relevance score) that can be reused as the delta metric at near-zero extra cost.

## When NOT to Use It

- Tasks with no measurable delta between iterations, or where surface similarity is a poor proxy for actual progress (e.g., a long-form writing loop where two drafts can look textually similar but differ meaningfully in quality).
- Loops expected to have genuinely slow, incremental convergence, where several visually-similar iterations in a row are normal and expected rather than a sign of stalling — an aggressive patience window here causes false early stops.
- Situations where the cost of a false early stop (abandoning a task that was about to succeed) is much higher than the cost of a few wasted iterations — in that case, let the [Loop Termination](/AI-Engineering-Patterns/patterns/loop-engineering/loop-termination/) pattern's iteration ceiling be the only backstop.

## Trade-offs

1. **Metric choice is task-specific and can be wrong** — a delta metric tuned for code diffs doesn't transfer to open-ended text generation, and a poorly chosen metric can either miss real stalls or flag false ones.
2. **Patience window tuning** — too short, and slow-but-real progress gets mistaken for a plateau; too long, and the pattern provides little savings over just running to the ceiling.
3. **Added per-iteration compute** — computing a delta (especially embedding-based) has a real cost, which needs to be weighed against the savings from stopping early.
4. **Metric gaming** — a loop can settle into an output that scores as "improving" on the chosen delta metric while making no real progress on the actual task, if the metric and the task diverge.

## Failure Modes

### False Plateau
**Trigger**: The delta metric shows near-zero change between iterations, but the underlying content actually differs in a way that matters for the task (e.g., a one-line but critical fix that a text-similarity metric treats as a negligible edit).
**Symptom**: The loop terminates as "stalled" just before it would have succeeded.
**Mitigation**: Prefer task-specific progress signals (test-pass count, schema-validity score) over generic text similarity whenever one is available; reserve generic similarity metrics for cases with no better option.

### Undetected Oscillation
**Trigger**: The patience window or cycle-length check is too short to catch a 3-or-more-state oscillation cycle.
**Symptom**: The loop keeps cycling and only stops when it eventually hits the iteration ceiling, defeating the purpose of this pattern.
**Mitigation**: Check for repeating cycles of at least 2-4 states, not just exact-repeat-of-the-immediately-prior-state, and size the patience window to be at least twice the longest cycle length you expect to catch.

### Metric-Task Mismatch
**Trigger**: The chosen delta metric measures something correlated with, but not identical to, actual task progress.
**Symptom**: The loop reports "improving" while the actual output quality is flat or worsening, or reports "stalled" on a loop that was genuinely progressing slowly.
**Mitigation**: Validate the delta metric against a held-out set of known-good and known-stalled loop traces before relying on it in production; treat metric selection as itself requiring evaluation, not a one-time assumption.

## Implementation Example

```python
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class ProgressState:
    history: list
    patience: int = 3


def default_similarity(a: str, b: str) -> float:
    # Minimal placeholder: word-overlap ratio. Replace with an
    # embedding-based or task-specific metric in production.
    words_a, words_b = set(a.split()), set(b.split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def detect_plateau(
    history: list,
    patience: int,
    similarity_fn: Callable[[str, str], float] = default_similarity,
    threshold: float = 0.95,
) -> bool:
    if len(history) < patience + 1:
        return False
    window = history[-(patience + 1):]
    return all(
        similarity_fn(window[i], window[i + 1]) >= threshold
        for i in range(len(window) - 1)
    )


def detect_oscillation(history: list, max_cycle_length: int = 4) -> bool:
    for cycle_len in range(2, max_cycle_length + 1):
        if len(history) < cycle_len * 2:
            continue
        recent = history[-cycle_len * 2:]
        first_half, second_half = recent[:cycle_len], recent[cycle_len:]
        if first_half == second_half:
            return True
    return False


def no_progress_check(history: list, patience: int = 3) -> Optional[str]:
    if detect_oscillation(history):
        return "oscillating"
    if detect_plateau(history, patience):
        return "plateaued"
    return None
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| sentence-transformers / OpenAI embeddings | Embedding libraries | Common backbone for semantic delta scoring between iterations |
| difflib / Levenshtein libraries | Open-source | Cheap text-delta metrics for code diffs and short text |
| Custom task-specific scorers (test-pass count, schema validators) | Task-specific | Usually the highest-signal option when available; prefer these over generic similarity |
| LangGraph checkpoints | Framework | Can be inspected across steps to build a rolling history for delta computation |

## Related Patterns

- **[Loop Termination](/AI-Engineering-Patterns/patterns/loop-engineering/loop-termination/)** — this pattern supplies one of the three signals that Loop Termination consumes.
- **[Reflexion Loop](/AI-Engineering-Patterns/patterns/loop-engineering/reflexion-loop/)** — a common loop shape where oscillation between two corrected-and-re-broken states is a frequently observed failure.
- **[Embedding Drift Detector](/AI-Engineering-Patterns/patterns/observability/embedding-drift-detector/)** — a related idea applied across time in production monitoring rather than within a single loop's iterations.

## Further Reading

- [Loop Engineering (2026): Self-Prompting AI Agent Patterns — Agent Shortlist](https://agentshortlist.com/articles/loop-engineering)
- [What Is Loop Engineering? — MindStudio](https://www.mindstudio.ai/blog/what-is-loop-engineering-ai-coding-agents)
- [Reflexion: Language Agents with Verbal Reinforcement Learning (Shinn et al., 2023)](https://arxiv.org/abs/2303.11366)