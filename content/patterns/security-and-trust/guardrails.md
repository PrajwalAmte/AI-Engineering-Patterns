---
title: Guardrails
pillar: security-and-trust
status: validated-in-production
tags: [validation, security, output-filtering, tool-use, safety]
related:
  - Input Sanitization
  - Tool Output Firewall
  - Human-in-the-Loop
  - Span-Level Tracing
example: examples/security_and_trust/guardrails.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Checks in code, outside the model, at the input, output and tool boundaries. They run in parallel with a deadline, log every verdict, and fail closed when a safety check breaks.
sidebar:
  order: 3
---

## What It Is

A guardrail is a check that runs *outside* the model and can stop the pipeline. You put them at three boundaries:

- **Input**: before the user's message reaches the model. Off-topic requests, abuse, injection scores.
- **Output**: before the answer reaches the user. Leaked system prompt, policy violations, invalid format, unsupported claims.
- **Tool calls**: before a tool executes. Is this tool allowed here? Are the arguments within limits? Does a human need to approve it?

The key property is that guardrails are code. A rule written only in the system prompt ("never discuss competitors") holds until the right rephrasing comes along. A guardrail in code holds regardless of what the model was talked into.

## The Problem It Solves

Prompt-only safety fails on the inputs you didn't think of. One clever message gets the support bot giving medical advice, or printing its instructions, or calling `issue_refund` for $5,000. The worst part is that you find out from a screenshot, not from your logs.

Agents raise the stakes. Once the model can send email, write to a database or spend money, the question changes from "might it say something bad?" to "what can it *do* if someone takes control of it?" The tool boundary is where you answer that question.

## How It Works

<pre class="mermaid">
flowchart TD
    U["User input"] --> IG["Input guardrails<br/>(parallel, deadline)"]
    IG -->|"tripped"| B1["Generic refusal; reason → audit log"]
    IG -->|"pass"| M["Model"]
    M -->|"tool call"| TG["Tool policy:<br/>allowlist · approval · argument limits"]
    TG -->|"blocked"| E["Error returned to the model"]
    TG -->|"ok"| T["Execute tool"]
    T --> M
    M --> OG["Output guardrails<br/>(parallel, deadline)"]
    OG -->|"tripped"| B2["Safe fallback; reason → audit log"]
    OG -->|"pass"| R["Response"]
</pre>

1. **Each guardrail is a function** that returns a verdict: tripped or not, plus a reason.
2. **Run a boundary's checks in parallel,** under a deadline. A moderation API that hangs must not hang the product.
3. **Declare failure behavior per guardrail.** If a safety check crashes or times out, *block* (fail closed). If a nice-to-have like a tone checker crashes, let the request through (fail open).
4. **Tool calls go through a policy:** an allowlist per context, human approval for destructive actions, and argument validators ("refund ≤ $100"). A blocked call returns an error to the model, which can then explain or try something else.
5. **Log every verdict,** pass or fail, with the boundary, guardrail name and reason. This is your audit trail and your false-positive dataset.
6. **Show users a generic message.** Telling an attacker *which* guardrail fired helps them get around it.

A cheap, reliable output check: put a unique canary string in your system prompt. If it ever appears in an output, the prompt leaked.

## When to Use It

- The assistant is public-facing, or users may be adversarial.
- The model has tools with side effects, or access to data some users shouldn't see.
- One bad response would be a real problem: regulated industries, brand risk, money movement.

## When NOT to Use It

- **Internal, read-only, low-stakes tools.** A team-internal summarizer with no tools may need nothing beyond the model's own safety training.
- **As a substitute for least privilege.** If the agent holds a database credential that can drop tables, no guardrail makes that safe. Remove the capability first, then guard what's left.

## Trade-offs

- **Latency.** Each boundary adds the slowest check's latency, plus the deadline. Run checks in parallel, keep them cheap, and reserve model-based checks for high-risk paths.
- **False positives.** An over-eager topic filter blocks legitimate questions, and users decide the product is useless. The audit log is how you tune it.
- **Streaming conflicts with output checks.** You can't check an answer you've already streamed. Either buffer (adding latency), check in chunks, or accept that output guardrails can only stop *later* messages.

## Failure Modes

**Fail-open by accident.** The moderation call throws, the exception is caught and logged, and the response goes out unchecked. Make fail-closed the default and opt out explicitly for each non-safety check.

**Guardrails that only exist in the prompt.** "The assistant must never issue refunds over $100" sits in the system prompt while `issue_refund` has no limit in code. Every rule that matters needs an enforcement point the model can't talk its way past.

**Silent guardrails.** Blocks aren't logged, so you can't tell attacks from false positives, and nobody tunes anything. Record verdicts as spans or events ([Span-Level Tracing](../observability-and-evaluation/span-level-tracing.md)).

## Implementation Example

Parallel guardrails per boundary with a real deadline, fail-closed and fail-open behavior, an audit log, generic user messages, a canary-based leak check, and a tool policy with an allowlist, approval and argument validators. The tests include a guardrail that hangs and one that crashes.

```bash
cd examples && pytest security_and_trust/test_guardrails.py
```

<!-- example: examples/security_and_trust/guardrails.py -->
```python
"""Guardrails.

Checks that run outside the model at three boundaries: input, output, and
before a tool executes. Checks at a boundary run in parallel within a time
budget, any tripwire blocks, every verdict is logged, and each guardrail
declares what happens if it crashes or times out (fail closed for safety
checks, open for nice-to-haves).
"""

from __future__ import annotations

import concurrent.futures as cf
import re
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Verdict:
    tripped: bool
    reason: str = ""


@dataclass
class Guardrail:
    name: str
    check: Callable[[str], Verdict]
    fail_closed: bool = True  # if the check errors or times out, block


@dataclass
class ToolPolicy:
    allowed: set[str]
    needs_approval: set[str] = field(default_factory=set)  # destructive tools
    validators: dict[str, Callable[[dict], str | None]] = field(default_factory=dict)  # -> error or None


class Blocked(Exception):
    def __init__(self, boundary: str, guardrail: str, reason: str):
        super().__init__(f"{boundary}/{guardrail}: {reason}")
        self.boundary, self.guardrail, self.reason = boundary, guardrail, reason


@dataclass
class GuardedPipeline:
    llm: Callable[[str], str]
    input_rails: list[Guardrail]
    output_rails: list[Guardrail]
    timeout_s: float = 2.0
    audit: list[dict] = field(default_factory=list)

    def _run(self, boundary: str, rails: list[Guardrail], text: str) -> None:
        pool = cf.ThreadPoolExecutor(max_workers=max(1, len(rails)))
        try:
            futures = {pool.submit(r.check, text): r for r in rails}
            done, _ = cf.wait(futures, timeout=self.timeout_s)
            for future, rail in futures.items():
                if future not in done:
                    verdict = Verdict(rail.fail_closed, f"timed out after {self.timeout_s}s")
                else:
                    try:
                        verdict = future.result()
                    except Exception as exc:
                        verdict = Verdict(rail.fail_closed, f"guardrail error: {exc}")
                self.audit.append(
                    {"boundary": boundary, "guardrail": rail.name, "tripped": verdict.tripped, "reason": verdict.reason}
                )
                if verdict.tripped:
                    raise Blocked(boundary, rail.name, verdict.reason)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)  # never wait on a hung check

    def respond(self, user_input: str) -> str:
        try:
            self._run("input", self.input_rails, user_input)
            answer = self.llm(user_input)
            self._run("output", self.output_rails, answer)
            return answer
        except Blocked as b:
            # Users get a generic message; the specific reason goes to the audit log.
            return "Sorry, I can't help with that request." if b.boundary == "input" else "Sorry, something went wrong."


def authorize_tool(policy: ToolPolicy, name: str, args: dict, approved: bool = False) -> None:
    """Run before every tool execution. Raises Blocked; the error goes back to the model."""
    if name not in policy.allowed:
        raise Blocked("tool", "allowlist", f"tool {name!r} is not allowed here")
    if name in policy.needs_approval and not approved:
        raise Blocked("tool", "approval", f"{name!r} needs human approval")
    if (validate := policy.validators.get(name)) and (error := validate(args)):
        raise Blocked("tool", "arguments", error)


# --- a few example checks ---------------------------------------------------

def off_topic(allowed_topics: list[str]) -> Callable[[str], Verdict]:
    pattern = re.compile("|".join(map(re.escape, allowed_topics)), re.I)
    return lambda text: Verdict(not pattern.search(text), "off topic")


def leaks_system_prompt(secret_marker: str) -> Callable[[str], Verdict]:
    # Put a unique canary string in your system prompt; if it ever appears in output, it leaked.
    return lambda text: Verdict(secret_marker in text, "system prompt leaked")
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| OpenAI Agents SDK guardrails | Input and output guardrails with tripwires, built in |
| NVIDIA NeMo Guardrails | Programmable rails (Colang) for dialogue, topics and tool use |
| Guardrails AI | Validator hub for output structure and content |
| Llama Guard, ShieldGemma | Open safety classifiers for input and output moderation |
| Cloud moderation APIs | OpenAI Moderation, Azure AI Content Safety, AWS Bedrock Guardrails |

## Related Patterns

- [Input Sanitization](input-sanitization.md) is the pre-processing layer before the input guardrails.
- [Tool Output Firewall](tool-output-firewall.md) guards what comes *back* from tools. The tool policy here guards what goes *out*.
- [Human-in-the-Loop](../governance/human-in-the-loop.md) is what "needs approval" connects to.
- [Span-Level Tracing](../observability-and-evaluation/span-level-tracing.md) is where guardrail verdicts should end up.

## Further Reading

- [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/). See especially LLM01 (Prompt Injection) and LLM06 (Excessive Agency).
- [OpenAI Agents SDK: Guardrails](https://openai.github.io/openai-agents-python/guardrails/)
- [Design Patterns for Securing LLM Agents against Prompt Injections](https://arxiv.org/abs/2506.08837), Beurer-Kellner et al., 2025
