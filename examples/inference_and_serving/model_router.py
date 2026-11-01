"""Model Router.

Send each query to the cheapest model tier that can handle it, and escalate
when the cheap answer fails a check. Start with rules like these; replace the
scoring function with a trained classifier once you have labelled traffic.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

REASONING_HINTS = re.compile(
    r"\b(why|explain|compare|trade-?offs?|prove|design|debug|step by step|analy[sz]e|plan)\b", re.I
)
CODE_HINTS = re.compile(r"```|def |class |SELECT |stack trace|Traceback", re.I)


@dataclass
class Tier:
    name: str
    model: Callable[[str], str]
    max_score: float  # this tier takes queries scoring up to this value


def complexity_score(query: str, turns: int = 1) -> float:
    """0.0 = trivial lookup, 1.0 = hard multi-step reasoning. Crude on purpose."""
    score = min(len(query.split()) / 200, 0.4)
    score += 0.25 * min(len(REASONING_HINTS.findall(query)), 2)
    score += 0.2 if CODE_HINTS.search(query) else 0.0
    score += 0.1 if turns > 6 else 0.0
    return min(score, 1.0)


@dataclass
class ModelRouter:
    tiers: list[Tier]  # cheapest first
    accept: Callable[[str, str], bool] = lambda query, answer: bool(answer.strip())
    stats: Counter = field(default_factory=Counter)

    def pick(self, query: str, turns: int = 1) -> int:
        score = complexity_score(query, turns)
        for i, tier in enumerate(self.tiers):
            if score <= tier.max_score:
                return i
        return len(self.tiers) - 1

    def answer(self, query: str, turns: int = 1) -> tuple[str, str]:
        """Returns (answer, tier_name). Escalates one tier at a time on rejection."""
        start = self.pick(query, turns)
        self.stats[f"routed:{self.tiers[start].name}"] += 1
        answer = ""
        for tier in self.tiers[start:]:
            answer = tier.model(query)
            if self.accept(query, answer):
                return answer, tier.name
            # Track escalations per tier: a rising rate means the router or the
            # cheap model has drifted, long before average quality moves.
            self.stats[f"escalated_from:{tier.name}"] += 1
        return answer, self.tiers[-1].name
