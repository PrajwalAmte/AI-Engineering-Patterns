"""LLM-as-Judge.

A judge model scores outputs against a rubric whose levels are described
concretely. Two habits make the scores worth trusting: pairwise comparisons
are run in both orders (judges favour whichever answer they read first), and
the judge is checked against human labels before anyone believes its numbers.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

Judge = Callable[[str], str]

RUBRIC = """Score the RESPONSE to the QUESTION for correctness and helpfulness.
1 = wrong or harmful. 2 = partly right but misleading or missing the key point.
3 = right but incomplete or padded. 4 = right, complete and concise.
Judge substance only; length and confidence are not quality.
Reply with JSON: {"reasoning": "<one or two sentences>", "score": 1|2|3|4}"""

PAIRWISE = """Which response answers the QUESTION better? Judge substance, not length.
Reply with JSON: {"reasoning": "<one sentence>", "winner": "A"|"B"|"tie"}"""


def _parse(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    return json.loads(raw[start : end + 1])


def score(judge: Judge, question: str, response: str, reference: str | None = None) -> int | None:
    prompt = f"{RUBRIC}\n\nQUESTION:\n{question}\n\nRESPONSE:\n{response}"
    if reference:
        prompt += f"\n\nREFERENCE ANSWER (for checking facts):\n{reference}"
    try:
        value = int(_parse(judge(prompt))["score"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None  # count unparseable verdicts separately; don't guess
    return value if 1 <= value <= 4 else None


def compare(judge: Judge, question: str, a: str, b: str) -> str:
    """Returns "A", "B" or "tie". Runs both orders; disagreement means tie."""

    def ask(first: str, second: str) -> str:
        raw = judge(f"{PAIRWISE}\n\nQUESTION:\n{question}\n\nRESPONSE A:\n{first}\n\nRESPONSE B:\n{second}")
        try:
            return _parse(raw)["winner"]
        except (KeyError, json.JSONDecodeError):
            return "tie"

    forward = ask(a, b)
    backward = {"A": "B", "B": "A"}.get(ask(b, a), "tie")  # map back to original labels
    return forward if forward == backward else "tie"


@dataclass
class Agreement:
    exact: float  # judge == human
    within_one: float  # |judge - human| <= 1
    unparseable: int


def agreement_with_humans(judge: Judge, labelled: list[tuple[str, str, int]]) -> Agreement:
    """Run this before trusting the judge, and again whenever you change judge model or rubric."""
    exact = near = bad = 0
    for question, response, human in labelled:
        s = score(judge, question, response)
        if s is None:
            bad += 1
            continue
        exact += s == human
        near += abs(s - human) <= 1
    n = len(labelled) or 1
    return Agreement(exact / n, near / n, bad)
