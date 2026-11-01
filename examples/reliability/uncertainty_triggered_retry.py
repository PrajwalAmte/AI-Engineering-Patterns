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
