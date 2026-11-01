"""Circuit Breaker for LLMs.

Counts slow and empty completions as failures, not just exceptions, because
LLM providers usually degrade with a 200 OK.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from enum import Enum


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: float = 0.5,  # trip when half the window failed...
        window: int = 20,
        min_calls: int = 10,  # ...but never on fewer than this many calls
        cooldown_s: float = 30.0,
        probes_to_close: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.failure_threshold = failure_threshold
        self.min_calls = min_calls
        self.cooldown_s = cooldown_s
        self.probes_to_close = probes_to_close
        self._clock = clock
        self._results: deque[bool] = deque(maxlen=window)
        self._state = State.CLOSED
        self._opened_at = 0.0
        self._probe_successes = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> State:
        with self._lock:
            return self._current_state()

    def allow(self) -> bool:
        return self.state is not State.OPEN

    def record(self, ok: bool) -> None:
        with self._lock:
            if self._current_state() is State.HALF_OPEN:
                if not ok:
                    self._trip()
                    return
                self._probe_successes += 1
                if self._probe_successes >= self.probes_to_close:
                    self._state = State.CLOSED
                    self._results.clear()
                return

            self._results.append(ok)
            if len(self._results) >= self.min_calls:
                failure_rate = self._results.count(False) / len(self._results)
                if failure_rate >= self.failure_threshold:
                    self._trip()

    def _current_state(self) -> State:
        if self._state is State.OPEN and self._clock() - self._opened_at >= self.cooldown_s:
            self._state = State.HALF_OPEN
            self._probe_successes = 0
        return self._state

    def _trip(self) -> None:
        self._state = State.OPEN
        self._opened_at = self._clock()
        self._results.clear()


def complete(
    prompt: str,
    primary: Callable[[str], str],
    fallback: Callable[[str], str],
    breaker: CircuitBreaker,
    latency_budget_s: float = 10.0,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[str, str]:
    """Returns (text, which_provider_answered)."""
    if breaker.allow():
        start = clock()
        try:
            text = primary(prompt)
        except Exception:
            breaker.record(False)
        else:
            usable = bool(text.strip())
            breaker.record(usable and clock() - start <= latency_budget_s)
            # A slow answer still counts against the provider, but the user
            # already waited for it, so hand it back rather than waiting twice.
            if usable:
                return text, "primary"
    return fallback(prompt), "fallback"
