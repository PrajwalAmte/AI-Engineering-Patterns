"""Grounding Verifier.

After generation, check every factual sentence against the passages that were
actually in the prompt. Unsupported sentences are flagged, removed, or sent
back for one rewrite. Numbers get special treatment: a claim containing a
number is only grounded if a supporting passage contains that same number.

The default `support` scorer is lexical so this runs offline. In production,
swap in an NLI or cross-encoder model with the same signature.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

STOPWORDS = set("a an the is are was were be been of to in on for and or with by at as it this that from".split())
NUMBER = re.compile(r"\d+(?:[.,]\d+)*%?")
SENTENCE = re.compile(r"(?<=[.!?])\s+")
NOT_A_CLAIM = re.compile(r"^(i think|you (can|should|might)|let me|please|feel free|hope this)\b|\?$", re.I)


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS}


def lexical_support(claim: str, passage: str) -> float:
    words = content_words(claim)
    if not words:
        return 1.0
    return len(words & content_words(passage)) / len(words)


@dataclass
class Verdict:
    claim: str
    grounded: bool
    source: int | None  # index of the supporting passage
    score: float


@dataclass
class VerifiedAnswer:
    text: str
    verdicts: list[Verdict] = field(default_factory=list)

    @property
    def ungrounded(self) -> list[str]:
        return [v.claim for v in self.verdicts if not v.grounded]


def extract_claims(response: str) -> list[str]:
    sentences = [s.strip() for s in SENTENCE.split(response) if s.strip()]
    return [s for s in sentences if not NOT_A_CLAIM.search(s)]


def check(
    claim: str, passages: list[str], support: Callable[[str, str], float], threshold: float
) -> Verdict:
    numbers = set(NUMBER.findall(claim))
    best, best_score = None, 0.0
    for i, passage in enumerate(passages):
        if numbers and not numbers <= set(NUMBER.findall(passage)):
            continue  # a passage that doesn't contain the number can't support it
        score = support(claim, passage)
        if score > best_score:
            best, best_score = i, score
    return Verdict(claim, best_score >= threshold, best, best_score)


def verify(
    response: str,
    passages: list[str],
    policy: str = "flag",  # "flag" | "suppress" | "regenerate"
    llm: Callable[[str], str] | None = None,
    support: Callable[[str, str], float] = lexical_support,
    threshold: float = 0.6,
) -> VerifiedAnswer:
    verdicts = [check(c, passages, support, threshold) for c in extract_claims(response)]
    bad = [v.claim for v in verdicts if not v.grounded]

    if bad and policy == "regenerate" and llm is not None:
        rewrite = llm(
            "Rewrite the answer using only facts stated in the sources. Remove these unsupported claims:\n"
            + "\n".join(f"- {c}" for c in bad)
            + "\n\nSources:\n" + "\n".join(passages) + f"\n\nAnswer:\n{response}"
        )
        # One rewrite only. If it still isn't grounded, fall back to suppression
        # rather than looping on a model that keeps reaching for the same claim.
        return verify(rewrite, passages, policy="suppress", support=support, threshold=threshold)

    text = response
    for v in verdicts:
        if v.grounded:
            text = text.replace(v.claim, f"{v.claim} [{v.source + 1}]", 1)
        elif policy == "suppress":
            text = text.replace(v.claim, "", 1)
        else:
            text = text.replace(v.claim, f"{v.claim} [unverified]", 1)
    return VerifiedAnswer(" ".join(text.split()), verdicts)
