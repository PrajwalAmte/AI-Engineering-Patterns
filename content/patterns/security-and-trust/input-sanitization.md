---
title: Input Sanitization
pillar: security-and-trust
status: validated-in-production
tags: [security, prompt-injection, pii, input-validation]
related:
  - Output Validation Pattern
  - Schema-Enforced Input Pattern
  - Structured Output Enforcement
  - PII Scrubbing Pipeline
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Filter prompt injection, jailbreaks, and PII before queries reach the model.
sidebar:
  order: 1
---

## What It Is

Input sanitization is a defense layer that inspects, classifies, and transforms user input before it reaches the LLM. It detects and blocks prompt injection attacks, jailbreak attempts, and PII leakage at the input boundary — the same way web applications sanitize form inputs before passing them to a database.

## The Problem It Solves

LLMs process user input as part of their prompt. Unlike traditional software where input and instructions are structurally separated, LLMs treat everything as text in the same context window. This creates a fundamental vulnerability:

- **Prompt injection**: Malicious instructions embedded in user input that override the system prompt ("Ignore previous instructions and...").
- **Jailbreaks**: Attempts to bypass safety constraints through social engineering, role-playing scenarios, or encoding tricks.
- **PII in prompts**: Users inadvertently (or intentionally) including personal data that gets sent to external model providers, logged, or used in training.

Without input sanitization, every user query is a potential attack surface.

## How It Works

<pre class="mermaid">
flowchart TD
    A["User input"] --> B["Length + format validation"]
    B --> C{"Valid?"}
    C -->|"No"| X["Reject with safe error"]
    C -->|"Yes"| D["PII detection and redaction"]
    D --> E["Prompt-injection detection"]
    E --> F{"Flagged as adversarial?"}
    F -->|"Yes"| G["Block, log incident, return safe response"]
    F -->|"No"| H["Forward sanitized input to model"]
</pre>

1. **Format validation**: Check input length, encoding, and structure. Reject inputs that exceed token budgets or contain suspicious encoding.
2. **PII detection**: Scan for patterns matching personal data (emails, phone numbers, SSNs, credit card numbers). Redact or tokenize detected PII before the input moves forward.
3. **Injection detection**: Classify the input for known injection patterns using one or more methods:
   - **Pattern matching**: Regular expressions for common injection prefixes ("ignore previous", "system:", delimiter injection).
   - **Perplexity detection**: Inputs with unusual token distributions may contain injected instructions.
   - **Classifier model**: A fine-tuned model that classifies inputs as benign or adversarial.
4. **Decision**: Clean inputs proceed to the model. Flagged inputs are blocked, logged for security review, and the user receives a generic safe response.

## When to Use It

- Your system accepts free-text user input that is incorporated into LLM prompts.
- Your application handles any type of sensitive or personal data.
- You expose LLM functionality to external or untrusted users.
- Compliance requirements (GDPR, HIPAA, PCI-DSS) mandate input data handling controls.

## When not to Use It

- The system only processes internal, pre-validated data that never includes user input (batch processing of structured records). Sanitization adds latency to a path that does not need it.
- You use structured input exclusively (API calls with typed parameters, not free text). Schema validation is more appropriate than text-level sanitization.
- The LLM has no tools, no access to sensitive data, and no actions beyond text generation in a sandboxed environment. The blast radius of a successful injection is limited to the response text itself.

## Trade-offs

1. **False positives** — Aggressive injection detection blocks legitimate queries that happen to contain patterns resembling attacks. "Please ignore the previous error and retry" is a valid user request that matches injection patterns.
2. **Latency** — Each sanitization step adds processing time. PII detection with NER models can add 10-50ms. Classifier-based injection detection adds more.
3. **Arms race** — Injection techniques evolve continuously. Pattern-based detection has a short half-life as attackers find new phrasings. Classifier models require ongoing retraining.
4. **Incomplete coverage** — No sanitization layer catches everything. Sophisticated indirect injection (through retrieved documents, tool outputs, or multi-turn context manipulation) bypasses input-level checks.

## Failure Modes

### Regex-Based Detection Bypass
**Trigger**: Attacker uses Unicode homoglyphs, zero-width characters, or language switching to evade pattern-based injection detection.
**Symptom**: Injection passes all regex filters and reaches the model. The attack is only discovered post-hoc through output monitoring or user reports.
**Mitigation**: Normalize Unicode before pattern matching. Layer a classifier-based detector on top of regex rules. Treat pattern matching as the first line of defense, not the only one.

### Overzealous PII Detection
**Trigger**: PII detection model flags domain-specific identifiers (product codes, internal IDs, medical terms) as personally identifiable information.
**Symptom**: Legitimate queries are blocked or have critical information redacted, producing useless model responses. Users complain about "the AI not understanding my question."
**Mitigation**: Fine-tune PII detection on domain-specific data. Maintain an allow-list of known entity patterns. Log false positives and review weekly.

### Multi-Turn Context Accumulation
**Trigger**: An attacker spreads a malicious instruction across multiple turns of conversation, each turn individually benign.
**Symptom**: Per-message sanitization passes every turn, but the concatenated context assembles a complete injection. The attack is invisible to single-turn analysis.
**Mitigation**: Run injection detection on the full accumulated context periodically, not just the latest message. Set a context window sanitization interval.

## Implementation Example

```python
import re
from dataclasses import dataclass
from enum import Enum


class ThreatLevel(Enum):
    CLEAN = "clean"
    PII_DETECTED = "pii_detected"
    INJECTION_SUSPECTED = "injection_suspected"
    BLOCKED = "blocked"


@dataclass
class SanitizationResult:
    threat_level: ThreatLevel
    sanitized_input: str
    detections: list[str]
    original_length: int


PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "ssn": re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
}

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.I),
    re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior|your)\s+instructions", re.I),
    re.compile(r"you\s+are\s+now\s+(?:a|an)\s+", re.I),
    re.compile(r"new\s+instruction[s]?\s*:", re.I),
    re.compile(r"system\s*(?:prompt|message)\s*:", re.I),
    re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<\|im_start\|>", re.I),
    re.compile(r"```\s*system", re.I),
]

MAX_INPUT_LENGTH = 10000
REDACTION_PLACEHOLDER = "[REDACTED]"


def sanitize_input(text: str) -> SanitizationResult:
    detections: list[str] = []
    original_length = len(text)
    sanitized = text

    if len(text) > MAX_INPUT_LENGTH:
        return SanitizationResult(
            threat_level=ThreatLevel.BLOCKED,
            sanitized_input="",
            detections=[f"Input exceeds maximum length: {len(text)} > {MAX_INPUT_LENGTH}"],
            original_length=original_length,
        )

    for pii_type, pattern in PII_PATTERNS.items():
        matches = pattern.findall(sanitized)
        if matches:
            detections.append(f"{pii_type}: {len(matches)} instance(s) redacted")
            sanitized = pattern.sub(REDACTION_PLACEHOLDER, sanitized)

    for pattern in INJECTION_PATTERNS:
        if pattern.search(sanitized):
            detections.append(f"Injection pattern detected: {pattern.pattern[:50]}")
            return SanitizationResult(
                threat_level=ThreatLevel.INJECTION_SUSPECTED,
                sanitized_input="",
                detections=detections,
                original_length=original_length,
            )

    if any("redacted" in d for d in detections):
        threat_level = ThreatLevel.PII_DETECTED
    else:
        threat_level = ThreatLevel.CLEAN

    return SanitizationResult(
        threat_level=threat_level,
        sanitized_input=sanitized,
        detections=detections,
        original_length=original_length,
    )


def enforce_sanitization(text: str) -> str:
    result = sanitize_input(text)

    if result.threat_level == ThreatLevel.BLOCKED:
        raise ValueError("Input blocked by sanitization policy")

    if result.threat_level == ThreatLevel.INJECTION_SUSPECTED:
        raise ValueError("Input blocked: potential prompt injection detected")

    return result.sanitized_input
```

For production systems, complement pattern-based detection with a trained classifier (e.g., a fine-tuned model on prompt injection datasets) and use a dedicated PII detection library (Presidio, Phileas) for higher accuracy across entity types and languages.

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| Presidio | Open-source (Microsoft) | PII detection and anonymization with pluggable NER backends |
| LLM Guard | Open-source | Input/output sanitization specifically designed for LLM applications |
| Rebuff | Open-source | Prompt injection detection using multiple detection strategies |
| Lakera Guard | Managed API | Real-time prompt injection and content moderation |
| NVIDIA NeMo Guardrails | Open-source | Programmable guardrails for LLM applications |

## Related Patterns

- **[Output Validation Pattern](/AI-Engineering-Patterns/patterns/security-and-trust/output-validation/)** — Sanitize inputs before the model; validate outputs after. Both layers are needed.
- **[Schema-Enforced Input Pattern](/AI-Engineering-Patterns/patterns/security-and-trust/schema-enforced-input/)** — Replace free text with structured input to eliminate injection surface entirely.
- **[Structured Output Enforcement](/AI-Engineering-Patterns/patterns/security-and-trust/structured-output-enforcement/)** — Constrain outputs to match a schema. Complements input sanitization.
- **[PII Scrubbing Pipeline](/AI-Engineering-Patterns/patterns/security-and-trust/pii-scrubbing/)** — Dedicated PII handling for data that flows into training and logging pipelines.
- **[Audit Trail Pattern](/AI-Engineering-Patterns/patterns/security-and-trust/audit-trail/)** — Log sanitization decisions for incident investigation and compliance.

## Further Reading

- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [Prompt Injection — Simon Willison](https://simonwillison.net/series/prompt-injection/)
- [Microsoft Presidio — PII Detection Documentation](https://microsoft.github.io/presidio/)
- [Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection (Greshake et al., 2023)](https://arxiv.org/abs/2302.12173)
