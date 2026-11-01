"""Deterministic stand-ins for models, so every example runs offline.

Each example takes plain callables (``llm(prompt) -> str``, ``embed(text) ->
list[float]``). In production you pass your real client; in the tests we pass
these fakes. Nothing here is clever on purpose: if a test passes, it passes
because of the pattern, not because the fake is doing the work.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Iterable

_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def count_tokens(text: str) -> int:
    """Rough token count: ~0.75 words per token is close enough for budgeting tests."""
    words = len(tokenize(text))
    return math.ceil(words * 4 / 3)


def embed(text: str, dim: int = 256) -> list[float]:
    """Hashed bag-of-words embedding. Texts that share words land close together."""
    vec = [0.0] * dim
    for word in tokenize(text):
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: Iterable[float], b: Iterable[float]) -> float:
    a, b = list(a), list(b)
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class ScriptedLLM:
    """An LLM that answers from a script.

    ``responses`` is either a list (returned in order, last one repeats) or a
    function of the prompt. Every prompt is recorded in ``calls`` so tests can
    assert on what the pattern actually sent.
    """

    def __init__(self, responses: list[str] | Callable[[str], str]):
        self._responses = responses
        self.calls: list[str] = []

    def __call__(self, prompt: str, **_: object) -> str:
        self.calls.append(prompt)
        if callable(self._responses):
            return self._responses(prompt)
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[index]


class FakeClock:
    """Manually advanced clock, so time-based logic is tested without sleeping."""

    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds
