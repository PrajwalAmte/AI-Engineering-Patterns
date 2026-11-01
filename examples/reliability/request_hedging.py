"""Request Hedging for LLMs.

Send to the primary. If it hasn't answered by the hedge delay (set from its
own recent p95), send the same request to a backup and take whichever
*acceptable* answer arrives first. Cancel the loser.

Only for requests without side effects: never hedge a tool call that writes.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

AsyncLLM = Callable[[str], Awaitable[str]]


class LatencyTracker:
    """Rolling window of observed latencies; the hedge delay follows the provider."""

    def __init__(self, window: int = 200, quantile: float = 0.95, default_s: float = 2.0, min_samples: int = 20):
        self.samples: deque[float] = deque(maxlen=window)
        self.quantile, self.default_s, self.min_samples = quantile, default_s, min_samples

    def observe(self, seconds: float) -> None:
        self.samples.append(seconds)

    def delay(self) -> float:
        if len(self.samples) < self.min_samples:
            return self.default_s
        ordered = sorted(self.samples)
        return ordered[min(int(len(ordered) * self.quantile), len(ordered) - 1)]


@dataclass
class HedgeResult:
    text: str
    winner: str
    hedged: bool
    latency_s: float


async def hedged_complete(
    prompt: str,
    primary: tuple[str, AsyncLLM],
    backup: tuple[str, AsyncLLM],
    tracker: LatencyTracker,
    accept: Callable[[str], bool] = lambda text: bool(text.strip()),
) -> HedgeResult:
    start = time.monotonic()
    names: dict[asyncio.Task, str] = {}

    def launch(name: str, call: AsyncLLM) -> None:
        names[asyncio.ensure_future(call(prompt))] = name

    launch(*primary)
    pending = set(names)
    done, pending = await asyncio.wait(pending, timeout=tracker.delay())
    hedged = False
    if not done:
        hedged = True
        launch(*backup)
        pending = set(names) - done

    try:
        while True:
            for task in done:
                if task.exception() is None and accept(task.result()):
                    elapsed = time.monotonic() - start
                    if names[task] == primary[0]:
                        tracker.observe(elapsed)
                    return HedgeResult(task.result(), names[task], hedged, elapsed)
            if not hedged:
                # Primary answered fast but badly: that's a reason to try the backup too.
                hedged = True
                launch(*backup)
                pending = set(names) - done
            if not pending:
                raise RuntimeError("no provider returned an acceptable answer")
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in pending:
            task.cancel()  # with streaming APIs, closing the connection stops billing
