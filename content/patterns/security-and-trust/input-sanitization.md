---
title: Input Sanitization
pillar: security-and-trust
status: validated-in-production
tags: [security, prompt-injection, pii, input-validation]
related:
  - Guardrails
  - Tool Output Firewall
  - Prompt Mutation Testing
  - LLM Gateway
example: examples/security_and_trust/input_sanitization.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Normalize, bound, redact and score user input before it reaches the model. Redaction is reliable; injection detection is only a speed bump.
sidebar:
  order: 1
---

## What It Is

A pre-processing step on everything a user types, run before it reaches a prompt:

1. **Normalize** Unicode, so look-alike characters and zero-width characters can't hide words.
2. **Bound** the length.
3. **Redact** personal data you don't want sent to a provider or written to logs.
4. **Score** the input for injection attempts: block the obvious ones and flag the suspicious ones.

The first three are dependable engineering. The fourth is useful but limited, and this page says so plainly, because over-trusting injection filters is how teams end up with agents that can be talked into anything.

## The Problem It Solves

Users paste things. Card numbers into a support chat, colleagues' emails into a summarizer, a 200-page contract into a box meant for one question. Without sanitization, all of that goes to a third-party API and into your traces.

Users also attack. Most attacks are copy-pasted: "ignore all previous instructions", fake `system:` lines, role-play setups. Some are disguised with full-width letters or zero-width spaces so a naive regex misses them. A cheap filter catches the copy-pasted majority and gives you a log of who's trying.

## How It Works

<pre class="mermaid">
flowchart LR
    I["User input"] --> N["NFKC normalize<br/>strip zero-width chars"]
    N --> L{"Length OK?"}
    L -->|"no"| B1["Block"]
    L -->|"yes"| R["Redact PII<br/>(email, SSN, phone, Luhn-valid cards)"]
    R --> S["Injection score<br/>(weighted signals)"]
    S -->|"< flag"| A["Allow"]
    S -->|"flag ≤ score < block"| F["Allow + log for review"]
    S -->|"≥ block"| B2["Block with a generic message"]
</pre>

- **Normalize first.** `ｉｇｎｏｒｅ` and `ign​ore` (with a zero-width space) both become `ignore` before any pattern runs.
- **Redact with validation.** A 16-digit number that fails the Luhn check is an order number, not a card. Redacting it breaks the user's question.
- **Score, don't match.** Several weak signals add up. "Pretend you are a pirate" alone gets flagged. Combined with "reveal your system prompt", it gets blocked.
- **Flag before you block.** Flagged inputs are allowed but logged. That log is where you'll find both new attacks and your false positives.

## When to Use It

- Free text from users goes into a prompt, which covers nearly every chat or assistant feature.
- You send data to a third-party model provider and have obligations about personal data.
- Your model has tools or data access, so a successful injection could do something.

## When NOT to Use It

- **Structured inputs only.** If the "input" is a typed API payload, validate it against a schema. Text sanitization is the wrong tool.
- **As your only injection defense.** No input filter stops a determined attacker, and none sees *indirect* injection, which arrives through documents and tool results rather than the chat box. Limit what the model can *do* ([Guardrails](guardrails.md)), and inspect what tools return ([Tool Output Firewall](tool-output-firewall.md)).

## Trade-offs

- **False positives cost real users.** "Please ignore the previous error and retry" is a legitimate request. Weighted scoring with separate flag and block thresholds keeps such requests flowing. A single regex that blocks would not.
- **Redaction can remove the point of the question.** "Why was my card ending 4242 charged twice?" may need the last four digits. Decide per field what to keep, mask or remove.
- **Patterns age.** Attack phrasing changes. Review flagged inputs periodically and update the signals, or add a hosted classifier.

## Failure Modes

**Obfuscation bypass.** Homoglyphs, zero-width characters, base64 and "translate this from French" tricks get past pattern filters. Normalization handles the first two. Nothing in this layer reliably handles the rest, which is why it can't be your only defense.

**Multi-turn assembly.** Each message is harmless on its own, and together they form an injection. Score the recent conversation window as well as the latest message.

**Redaction in the wrong place.** PII is redacted before the model call but logged raw by middleware that runs earlier. Put sanitization at the very first hop, usually the gateway.

## Implementation Example

Unicode normalization, a length limit, PII redaction with a Luhn check, weighted injection signals, and allow / flag / block thresholds. The tests include the bypass tricks and the false-positive case ("ignore the previous error").

```bash
cd examples && pytest security_and_trust/test_input_sanitization.py
```

<!-- example: examples/security_and_trust/input_sanitization.py -->
```python
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
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Microsoft Presidio | Open-source PII detection and anonymization (regex + NER) |
| Llama Prompt Guard, ProtectAI deberta injection classifier | Open models that classify injection and jailbreak attempts |
| Lakera Guard, Azure Prompt Shields | Hosted injection and jailbreak detection APIs |
| LLM Guard | Open-source input and output scanners bundled together |

## Related Patterns

- [Guardrails](guardrails.md) cover the output side and limit the damage when an injection gets through.
- [Tool Output Firewall](tool-output-firewall.md) handles the side door: injections inside documents and tool results.
- [Prompt Mutation Testing](../observability-and-evaluation/prompt-mutation-testing.md) checks whether your defenses hold under rephrasing.
- [LLM Gateway](../inference-and-serving/llm-gateway.md) is the right place for this to run, once for every caller.

## Further Reading

- [OWASP Top 10 for LLM Applications: LLM01 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- [Prompt injection explained](https://simonwillison.net/2023/May/2/prompt-injection-explained/), Simon Willison. Why filtering can't fully solve it.
- [Microsoft Presidio](https://microsoft.github.io/presidio/)
