"""Input Sanitization.

Normalise, bound, redact, and score user input before it reaches the model.

Be clear about what this buys you. PII redaction and length limits are
reliable. Injection *detection* is a speed bump: it stops the copy-pasted
attacks and gives you a signal to log, but a determined attacker will get
past any filter. The real defence is limiting what a successful injection can
do (see Guardrails and Tool Output Firewall).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)

PII = {
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "PHONE": re.compile(r"(?<!\d)\+?\d{1,2}[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"),
    "CARD": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
}

INJECTION_SIGNALS = [
    (re.compile(r"ignore (all )?(your |the )?(previous|prior|above) (instructions|rules|prompt)", re.I), 0.6),
    (re.compile(r"(reveal|print|show|repeat) (your |the )?(system prompt|instructions|hidden prompt)", re.I), 0.5),
    (re.compile(r"\byou are now\b|\bpretend (you are|to be)\b|\bact as\b.*\bno restrictions\b", re.I), 0.4),
    (re.compile(r"^\s*(system|assistant)\s*:", re.I | re.M), 0.4),
    (re.compile(r"</?(system|instructions?)>|\[/?INST\]", re.I), 0.4),
    (re.compile(r"\bDAN\b|developer mode|jailbreak", re.I), 0.3),
]


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


@dataclass
class Sanitized:
    text: str
    action: str  # "allow" | "flag" | "block"
    injection_score: float
    redactions: dict[str, int] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def normalize(text: str) -> str:
    # NFKC folds full-width and many look-alike characters; zero-width chars
    # are a favourite way to split "ignore" so a regex misses it.
    return unicodedata.normalize("NFKC", text).translate(ZERO_WIDTH)


def redact(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}

    def sub(kind: str, pattern: re.Pattern, s: str) -> str:
        def repl(m: re.Match) -> str:
            if kind == "CARD" and not _luhn_ok(re.sub(r"\D", "", m.group())):
                return m.group()  # an order number, not a card
            counts[kind] = counts.get(kind, 0) + 1
            return f"[{kind}]"

        return pattern.sub(repl, s)

    for kind in ("EMAIL", "SSN", "CARD", "PHONE"):  # card before phone: long digit runs
        text = sub(kind, PII[kind], text)
    return text, counts


def injection_score(text: str) -> tuple[float, list[str]]:
    score, reasons = 0.0, []
    for pattern, weight in INJECTION_SIGNALS:
        if pattern.search(text):
            score += weight
            reasons.append(pattern.pattern[:40])
    return min(score, 1.0), reasons


def sanitize(text: str, max_chars: int = 8000, flag_at: float = 0.4, block_at: float = 0.8) -> Sanitized:
    text = normalize(text)
    if len(text) > max_chars:
        return Sanitized(text[:max_chars], "block", 0.0, reasons=[f"input longer than {max_chars} chars"])
    text, redactions = redact(text)
    score, reasons = injection_score(text)
    action = "block" if score >= block_at else "flag" if score >= flag_at else "allow"
    return Sanitized(text, action, score, redactions, reasons)
