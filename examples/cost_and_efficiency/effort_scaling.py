"""Effort Scaling.

Decide up front how much a task deserves (model, tool calls, sub-agents,
tokens) and enforce it in code while the task runs. Log predicted vs actual
so the tiers can be recalibrated from data instead of hunches.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Effort:
    tier: str
    model: str
    max_tool_calls: int
    max_subagents: int
    max_output_tokens: int


TIERS = {
    "lookup": Effort("lookup", "small", max_tool_calls=3, max_subagents=0, max_output_tokens=300),
    "analysis": Effort("analysis", "medium", max_tool_calls=15, max_subagents=3, max_output_tokens=1500),
    "research": Effort("research", "large", max_tool_calls=60, max_subagents=8, max_output_tokens=4000),
}

COMPARE = re.compile(r"\b(compare|versus|vs\.?|differences?|trade-?offs?|pros and cons)\b", re.I)
OPEN_ENDED = re.compile(r"\b(research|landscape|survey|comprehensive|all (the )?options|deep dive|strategy)\b", re.I)


def classify(task: str) -> Effort:
    entities = len(re.findall(r"\b[A-Z][a-zA-Z0-9]+\b", task))
    if OPEN_ENDED.search(task) or entities >= 5:
        return TIERS["research"]
    if COMPARE.search(task) or len(task.split()) > 40:
        return TIERS["analysis"]
    return TIERS["lookup"]


class BudgetExhausted(Exception):
    pass


@dataclass
class Run:
    effort: Effort
    tool_calls: int = 0
    subagents: int = 0
    stopped_early: bool = False
    notes: list[str] = field(default_factory=list)

    def tool(self, fn: Callable[..., str], *args) -> str:
        if self.tool_calls >= self.effort.max_tool_calls:
            raise BudgetExhausted(f"{self.effort.tier}: {self.effort.max_tool_calls} tool calls used")
        self.tool_calls += 1
        return fn(*args)

    def spawn(self) -> None:
        if self.subagents >= self.effort.max_subagents:
            raise BudgetExhausted(f"{self.effort.tier}: no more sub-agents allowed")
        self.subagents += 1

    def record(self) -> dict:
        """One row per task: the data you recalibrate tiers from."""
        return {
            "tier": self.effort.tier,
            "tool_calls": self.tool_calls,
            "tool_budget": self.effort.max_tool_calls,
            "subagents": self.subagents,
            "hit_ceiling": self.tool_calls >= self.effort.max_tool_calls,
            "stopped_early": self.stopped_early,
        }
