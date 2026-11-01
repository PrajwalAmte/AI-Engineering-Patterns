"""Loop Termination.

One stop decision, checked after every step, in a fixed order:
1. goal check   -> stop: success
2. ceiling      -> stop: out of iterations or budget
3. no progress  -> stop: stalled
Every non-success stop returns the best result so far and a reason, so the
caller can show partial work or escalate instead of failing silently.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from loop_engineering.no_progress_detection import ProgressMonitor


@dataclass
class Outcome:
    reason: str  # "success" | "ceiling" | "budget" | "stalled"
    iterations: int
    result: str
    cost: float


def run_loop(
    step: Callable[[int, str | None], tuple[str, float]],  # (iteration, last_output) -> (output, cost)
    goal_met: Callable[[str], bool],
    max_iterations: int = 20,
    max_cost: float = float("inf"),
    monitor: ProgressMonitor | None = None,
    score: Callable[[str], float] | None = None,
) -> Outcome:
    monitor = monitor or ProgressMonitor()
    output, spent = None, 0.0
    for i in range(1, max_iterations + 1):
        output, cost = step(i, output)
        spent += cost
        trend = monitor.observe(output, score(output) if score else None)

        if goal_met(output):  # goal first: finishing on the last allowed step is still success
            return Outcome("success", i, output, spent)
        if spent >= max_cost:
            return Outcome("budget", i, monitor.best(), spent)
        if trend in ("plateau", "oscillating"):
            return Outcome("stalled", i, monitor.best(), spent)
    return Outcome("ceiling", max_iterations, monitor.best(), spent)
