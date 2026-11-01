---
title: No-Progress Detection
pillar: loop-engineering
status: emerging
tags: [agents, loops, stall-detection, oscillation]
related:
  - Loop Termination
  - Reflexion Loop
  - Semantic Rollback
example: examples/loop_engineering/no_progress_detection.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Notice when an agent loop keeps producing the same thing, or flips between a few things, and stop it before the iteration ceiling, keeping the best attempt.
sidebar:
  order: 2
---

## What It Is

A monitor that compares each iteration's output with recent ones and classifies the loop's trend:

- **Improving**: outputs differ and, if scored, aren't getting worse.
- **Plateau**: the same output (or a cosmetic variant) for several iterations in a row.
- **Oscillating**: bouncing between a few states (A → B → A → B).
- **Regressing**: the score dropped. Flag it, but keep going, because some paths dip before they improve.

On plateau or oscillation, the loop stops and returns the *best* iteration, which for an oscillating loop often isn't the last one.

## The Problem It Solves

An iteration ceiling guarantees the loop ends, but only after it has used every iteration. Two stall shapes are common:

- A coding agent applies the same patch for the fourth time, with a reworded commit message each time.
- A Reflexion-style loop where the reflection keeps "fixing" the actor back and forth between two approaches.

Both burn the remaining budget, and add latency, while producing nothing new.

## How It Works

<pre class="mermaid">
flowchart TD
    O["Iteration output (+ optional score)"] --> P{"Same as previous?<br/>(similarity ≥ threshold)"}
    P -->|"yes"| PL["plateau count +1"]
    P -->|"no"| OS{"Same as one of the<br/>2–3 before that?"}
    OS -->|"yes"| OC["oscillation count +1"]
    OS -->|"no"| R["reset counts"]
    PL & OC --> W{"Count ≥ patience?"}
    W -->|"yes"| STOP["Stalled → return best iteration"]
    W -->|"no"| GO["Continue"]
    R --> GO
</pre>

1. **Compare the state that matters,** such as the patch diff, the answer or the tool-call sequence. Not the whole context.
2. **Pick a similarity measure for the task.** Text similarity (as in the example) catches identical and near-identical outputs. Embedding similarity catches rewordings. A task metric (tests passing, score) catches "different text, no better".
3. **Use a patience window.** One repeat is normal. Two or three in a row is a stall.
4. **Look back a few steps** for cycles, not just one.
5. **Track the best iteration** by score when you have one, and return it on exit.

## When to Use It

- Agent loops with ceilings above five iterations or so, where early stalls waste real money.
- Self-refinement and reflection loops, which are especially prone to oscillation.

## When NOT to Use It

- **Short loops** (two or three iterations). The patience window would be most of the loop.
- **Exploratory loops** where revisiting earlier states is intentional (a search over options).

## Trade-offs

- **Threshold tuning.** A threshold that's too loose calls real progress a plateau. Too strict, and cosmetic rewording counts as progress. Tune it on logged loops.
- **Similarity misses semantic sameness.** Two different-looking patches can fail the same test for the same reason. Pair text similarity with a task signal (same failing test, same error).
- **The extra comparisons** are cheap for text, and less so with embeddings on every step.

## Failure Modes

**Cosmetic variation hides a plateau.** The agent changes a variable name each time and the text differs enough to look like progress. Compare normalized outputs (strip whitespace and comments), or compare outcomes (the same failing test).

**Stopping on a dip.** A regression gets treated as a stall, and the loop exits just before the fix. Treat regressing as a flag, not a stop.

**Returning the last output.** On an oscillating loop, the last state is a coin flip. Return the best-scored one.

## Implementation Example

Plateau and cycle detection with a patience window, a pluggable similarity function, a regression flag, and best-iteration tracking. The tests include an A/B flip-flop and a "fix" that only adds whitespace.

```bash
cd examples && pytest loop_engineering/test_no_progress_detection.py
```

<!-- example: examples/loop_engineering/no_progress_detection.py -->
```python
"""No-Progress Detection.

Watch what an agent loop produces each iteration and say when it has stopped
getting anywhere: the same output again and again (plateau), or bouncing
between a few outputs (oscillation). Return the best iteration seen, which for
an oscillating loop is often not the last one.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable
from dataclasses import dataclass, field

Similarity = Callable[[str, str], float]


def text_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


@dataclass
class ProgressMonitor:
    similarity: Similarity = text_similarity
    same_threshold: float = 0.97  # above this, two outputs count as "the same"
    patience: int = 2  # consecutive stalled iterations before we call it
    max_cycle: int = 3  # detect A-B-A and A-B-C-A cycles
    history: list[str] = field(default_factory=list)
    scores: list[float | None] = field(default_factory=list)
    _plateau: int = 0
    _oscillation: int = 0

    def observe(self, output: str, score: float | None = None) -> str:
        """Returns "improving", "regressing", "plateau" or "oscillating"."""
        prev = self.history[-1] if self.history else None
        self.history.append(output)
        self.scores.append(score)
        if prev is None:
            return "improving"

        if self.similarity(output, prev) >= self.same_threshold:
            self._plateau += 1
            self._oscillation = 0
        else:
            self._plateau = 0
            earlier = self.history[-1 - self.max_cycle : -2]
            if any(self.similarity(output, old) >= self.same_threshold for old in earlier):
                self._oscillation += 1
            else:
                self._oscillation = 0

        if self._plateau >= self.patience:
            return "plateau"
        if self._oscillation >= self.patience:
            return "oscillating"
        if score is not None and self.scores[-2] is not None and score < self.scores[-2]:
            return "regressing"  # worth flagging, not stopping: some paths dip before improving
        return "improving"

    def best(self) -> str:
        scored = [(s, i) for i, s in enumerate(self.scores) if s is not None]
        if scored:
            return self.history[max(scored)[1]]
        return self.history[-1]
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| difflib, rapidfuzz | Text similarity for plateau and cycle detection |
| Embedding models | Semantic similarity when rewording is common |
| Your test runner | The best progress signal for coding agents: did the set of failing tests change? |

## Related Patterns

- [Loop Termination](loop-termination.md) uses this as its stall signal.
- [Reflexion Loop](reflexion-loop.md) tends to oscillate. A repeated lesson is a related stall signal.
- [Semantic Rollback](semantic-rollback.md): when a step stalls, roll back and change strategy rather than repeating it.

## Further Reading

- [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366), Shinn et al., 2023. Includes discussion of when self-reflection stops helping.
- [Large Language Models Cannot Self-Correct Reasoning Yet](https://arxiv.org/abs/2310.01798), Huang et al., 2023
