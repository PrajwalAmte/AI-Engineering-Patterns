"""Maker-Verifier Split.

The agent that does the work never decides it's done. A separate verifier
checks the output against the task's own acceptance criteria, sees only the
output (never the maker's reasoning, which would talk it into agreeing), and
returns concrete issues the maker can act on. Repeated rejection, or a
verifier that can't decide, goes to a human.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Attempt:
    output: str
    rationale: str = ""  # maker's explanation: logged, never shown to the verifier


@dataclass
class Verdict:
    passed: bool
    issues: list[str] = field(default_factory=list)
    uncertain: bool = False


Maker = Callable[[str, list[str]], Attempt]  # (task, issues from last rejection) -> attempt
Verifier = Callable[[str, str], Verdict]  # (acceptance criteria, output) -> verdict


@dataclass
class Result:
    status: str  # "verified" | "escalated"
    output: str
    rounds: int
    history: list[tuple[str, Verdict]] = field(default_factory=list)


def run(task: str, criteria: str, maker: Maker, verifier: Verifier, max_rounds: int = 3) -> Result:
    issues: list[str] = []
    history: list[tuple[str, Verdict]] = []
    for round_no in range(1, max_rounds + 1):
        attempt = maker(task, issues)
        verdict = verifier(criteria, attempt.output)  # output only, by construction
        history.append((attempt.output, verdict))
        if verdict.uncertain:
            return Result("escalated", attempt.output, round_no, history)
        if verdict.passed:
            return Result("verified", attempt.output, round_no, history)
        issues = verdict.issues or ["verifier rejected the output without details"]
    return Result("escalated", history[-1][0], max_rounds, history)


def all_of(*checks: Callable[[str], str | None]) -> Callable[[str, str], Verdict]:
    """Build a mechanical verifier from checks that return an issue string or None.
    Mechanical checks (tests, schemas, linters) can't be persuaded; prefer them."""

    def verify(criteria: str, output: str) -> Verdict:
        issues = [msg for check in checks if (msg := check(output))]
        return Verdict(not issues, issues)

    return verify
