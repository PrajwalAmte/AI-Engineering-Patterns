"""Human-in-the-Loop.

An approval gate in the tool-execution layer, not in the prompt. Each action
is classified by risk; low-risk actions run, high-risk ones wait for a human
who can approve, edit or deny; some actions are never allowed. Silence is a
"no": an approval that times out is denied.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class Risk(Enum):
    AUTO = "auto"  # read-only or trivially reversible
    APPROVE = "approve"  # consequential: needs a human
    FORBID = "forbid"  # never, regardless of approval


@dataclass
class Action:
    tool: str
    args: dict
    reason: str  # the agent's stated reason, shown to the approver


@dataclass
class Decision:
    approved: bool
    args: dict | None = None  # approver may edit arguments before approving
    by: str = ""
    note: str = ""


Approver = Callable[[Action], Decision | None]  # None = no answer yet


@dataclass
class Gate:
    classify: Callable[[Action], Risk]
    ask: Approver
    timeout_s: float = 300.0
    poll_s: float = 0.0
    clock: Callable[[], float] = time.monotonic
    session_grants: set[str] = field(default_factory=set)  # "allow X for this task"
    audit: list[dict] = field(default_factory=list)

    def run(self, action: Action, execute: Callable[[str, dict], str]) -> str:
        risk = self.classify(action)
        if risk is Risk.FORBID:
            return self._done(action, risk, "denied", "forbidden action")
        if risk is Risk.AUTO or action.tool in self.session_grants:
            return self._done(action, risk, "auto", execute(action.tool, action.args))

        decision = self._wait(action)
        if decision is None:
            return self._done(action, risk, "denied", "no response before timeout")
        if not decision.approved:
            return self._done(action, risk, "denied", f"denied by {decision.by}: {decision.note}")
        args = decision.args if decision.args is not None else action.args
        return self._done(action, risk, f"approved by {decision.by}", execute(action.tool, args), args)

    def grant_for_session(self, tool: str) -> None:
        self.session_grants.add(tool)

    def _wait(self, action: Action) -> Decision | None:
        deadline = self.clock() + self.timeout_s
        while self.clock() < deadline:
            decision = self.ask(action)
            if decision is not None:
                return decision
            if self.poll_s:
                time.sleep(self.poll_s)
        return None

    def _done(self, action: Action, risk: Risk, outcome: str, result: str, args: dict | None = None) -> str:
        self.audit.append(
            {"tool": action.tool, "args": args or action.args, "reason": action.reason, "risk": risk.value,
             "outcome": outcome}
        )
        # The agent sees denials as tool results and has to adapt its plan.
        return result if not outcome.startswith("denied") else f"ACTION NOT TAKEN: {result}"


def default_classifier(action: Action) -> Risk:
    if action.tool in {"drop_table", "delete_account", "transfer_funds"}:
        return Risk.FORBID
    if action.tool.startswith(("get_", "search_", "read_", "list_")):
        return Risk.AUTO
    if action.tool == "issue_refund" and action.args.get("amount", 0) <= 20:
        return Risk.AUTO  # small refunds are cheaper to allow than to review
    return Risk.APPROVE
