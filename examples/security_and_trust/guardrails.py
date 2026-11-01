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
