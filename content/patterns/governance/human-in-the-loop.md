---
title: Human-in-the-Loop
pillar: governance
status: validated-in-production
tags: [governance, approval, agents, safety, audit]
related:
  - Guardrails
  - Tool Output Firewall
  - Model Card
  - Effort Scaling
example: examples/governance/human_in_the_loop.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: An approval gate in the tool-execution layer. Low-risk actions run, consequential ones wait for a person who can approve, edit or deny, and silence means no.
sidebar:
  order: 1
---

## What It Is

Before an agent's tool call executes, a gate classifies it by risk:

- **Auto**: read-only or trivially reversible. It runs immediately.
- **Approve**: consequential (sends something, changes something, costs something). It waits for a person.
- **Forbid**: never allowed in this context, whoever approves.

The approver sees what the agent wants to do, and why, and can approve it, edit the arguments first, or deny it. A denial goes back to the agent as a tool result so it can change its plan. An approval request that times out is a denial.

The essential detail is *where* the gate lives: in the code that executes tools, not in the prompt. "Always ask before sending email" in a system prompt is a request. A gate in the executor is a guarantee.

## The Problem It Solves

Agents make plausible mistakes with real consequences: the email goes to the wrong customer, the refund is 10× too large, the cleanup script deletes the wrong directory. And with tool output from the web or user content in context, the agent might not even be pursuing *your* goal ([Tool Output Firewall](../security-and-trust/tool-output-firewall.md)).

Asking for approval on *everything* fails differently. People approve without reading after the twentieth prompt, so the gate becomes a formality. The goal is to ask rarely, for the actions that matter, and make each request easy to judge.

## How It Works

<pre class="mermaid">
sequenceDiagram
    participant A as Agent
    participant G as Gate (tool executor)
    participant H as Human
    participant T as Tool
    A->>G: tool call + reason
    G->>G: classify risk
    alt auto, or granted for this session
        G->>T: execute
    else forbid
        G-->>A: ACTION NOT TAKEN (forbidden)
    else approve
        G->>H: "Agent wants to send_email to X because Y"
        alt approves (maybe with edits)
            H-->>G: approve
            G->>T: execute with final args
        else denies, or no answer before timeout
            G-->>A: ACTION NOT TAKEN (reason)
        end
    end
    G->>G: audit log entry
</pre>

1. **Classify by consequence, not by tool name alone.** A $15 refund and a $1,500 refund are the same tool with very different risk. Thresholds on arguments belong in the classifier.
2. **Show enough to decide.** Include the action, the exact arguments, and the agent's stated reason. An approver who has to dig for context will just click approve.
3. **Allow edits.** "Yes, but $50, not $500" is a common and valuable answer.
4. **Fail closed on timeout.** No answer means no action.
5. **Offer scoped session grants** ("allow file writes in this repo for this task") to cut repeated prompts without granting permanent permission.
6. **Audit everything:** what was proposed, by which agent, who decided, what actually ran.

## When to Use It

- Agents with write access to anything that matters: email, payments, production systems, customer records.
- Irreversible or externally visible actions.
- Regulated decisions where a named person must be accountable.

## When NOT to Use It

- **Read-only agents.** If the worst outcome is a wrong answer on screen, approval prompts are friction without a benefit.
- **High-volume, low-stakes actions.** Tagging tickets, drafting (not sending) replies. Sample them for review afterwards instead.
- **As a fix for an agent that's wrong too often.** If approvers reject 30% of proposals, fix the agent. Approval doesn't scale as a quality filter.

## Trade-offs

- **Latency measured in human time.** An agent waiting for approval can take minutes or hours. Design flows so the agent can carry on with other work, or end the turn cleanly, while it waits.
- **Approval fatigue.** Every unnecessary prompt makes the necessary ones less likely to be read. Track approval rates. A tool approved 99.9% of the time with no edits is a candidate for auto.
- **The classifier is a policy.** Someone has to own "what counts as consequential", and review it as tools are added.

## Failure Modes

**Rubber-stamping.** Approvers see 40 requests a day and approve them all in two seconds. Cut volume (auto-approve proven-safe actions), make requests easier to read, and spot-check that approvers catch planted bad requests.

**The gate lives in the prompt.** The agent is *told* to ask before acting, and a jailbreak or a confused plan skips the asking. The gate must be in the code path that executes the tool.

**Timeout defaults to yes.** "If nobody answers in 5 minutes, proceed" turns the gate into a delay. Default to no, and tell the user what's waiting.

## Implementation Example

A risk classifier (auto / approve / forbid, with argument thresholds), an approval wait with a timeout that denies, approval with edited arguments, session-scoped grants, denials returned to the agent as tool results, and an audit trail.

```bash
cd examples && pytest governance/test_human_in_the_loop.py
```

<!-- example: examples/governance/human_in_the_loop.py -->
```python
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
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| LangGraph `interrupt` | Pause a graph for human input and resume from a checkpoint |
| OpenAI Agents SDK, Claude Agent SDK | Tool approval hooks and permission modes |
| MCP clients | Per-tool confirmation in hosts such as Claude Desktop and IDEs |
| Temporal / workflow engines | Durable waits for long approval cycles |

## Related Patterns

- [Guardrails](../security-and-trust/guardrails.md): the tool policy there decides what needs approval, and this pattern handles the approving.
- [Tool Output Firewall](../security-and-trust/tool-output-firewall.md): after untrusted content enters the context, raise the approval level.
- [Model Card](model-card.md) documents the oversight setup for auditors.
- [Effort Scaling](../cost-and-efficiency/effort-scaling.md): larger budgets for autonomous work usually mean more actions that need approval.

## Further Reading

- [Our framework for developing safe and trustworthy agents](https://www.anthropic.com/news/our-framework-for-developing-safe-and-trustworthy-agents), Anthropic, 2025
- [LangGraph human-in-the-loop concepts](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/)
- [OWASP LLM06: Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
