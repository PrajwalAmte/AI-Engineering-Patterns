---
title: Multi-Agent Orchestration
pillar: inference-and-serving
status: validated-in-production
tags: [multi-agent, orchestration, delegation, agents]
related:
  - Effort Scaling
  - Context Compaction
  - Loop Termination
  - Span-Level Tracing
example: examples/inference_and_serving/multi_agent_orchestration.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: One agent plans and delegates narrow, non-overlapping subtasks to workers with fresh contexts, then combines their condensed results.
sidebar:
  order: 4
---

## What It Is

An orchestrator agent breaks a task into subtasks and hands each one to a worker agent. Each worker starts with a clean context containing only its objective, what's out of scope, and how much it may send back. Workers run in parallel where they can. The orchestrator reads their condensed findings and either plans another round or writes the final answer.

This is the "manager-as-tool" shape: workers are function calls, and control always returns to the orchestrator. The other common shape is *handoff*, where control moves to the specialist and stays there. Handoff suits conversational triage (routing a support chat to billing). Manager-as-tool suits research and analysis, where one place has to own the plan.

## The Problem It Solves

A single agent working on a broad task, say "compare these six vendors on security, pricing and integration", fills its context with search results and tool output long before it's finished. Early findings get pushed out or summarized away, and the agent loses track of what it already covered.

Splitting the work gives each subtask its own full context and lets independent subtasks run at the same time. Anthropic's write-up of its Research feature reports that this beat a single agent on breadth-heavy queries. The same write-up is candid that it costs many times the tokens.

## How It Works

<pre class="mermaid">
flowchart TD
    U["Task"] --> P["Orchestrator: plan<br/>≤ max_agents subtasks,<br/>each with objective + exclusions"]
    P --> W1["Worker 1<br/>fresh context"]
    P --> W2["Worker 2<br/>fresh context"]
    P --> W3["Worker N<br/>fresh context"]
    W1 & W2 & W3 -->|"condensed findings,<br/>≤ max_words each"| A["Orchestrator: done?"]
    A -->|"gaps remain and round < max_rounds"| P
    A -->|"done"| S["Synthesize final answer"]
</pre>

1. **Plan.** The orchestrator writes subtasks as structured output. Each has an objective and an explicit "not your job" line. That line does more to prevent duplicated work than anything else.
2. **Delegate.** Each worker gets only its subtask. Workers are often a cheaper model than the orchestrator.
3. **Condense.** Workers return findings, not raw tool output, and the orchestrator truncates anything over budget. Its context is the scarce resource.
4. **Re-plan or stop.** The orchestrator sees the findings and decides whether gaps remain. Subtasks that were already done aren't spawned again. Hard caps on agents per round and on rounds stop runaway fan-out.
5. **Synthesize** from the findings, not from the workers' full transcripts.

## When to Use It

- The task is wide: many sources, entities or angles that can be explored independently.
- One agent's context fills up before the work is done, even with compaction.
- The answer is valuable enough to justify many times the token cost of a single agent.

## When NOT to Use It

- **The task is a chain.** If every step depends on the one before, there's nothing to parallelize, and you get the cost without the speed.
- **The task is small.** One retrieval and one answer don't need a planner. Spawning agents for "what's our PTO policy" is the most common failure here.
- **You can't say where one subtask ends and the next begins.** If you can't write the exclusions, workers will overlap and duplicate each other.
- **Writing code together.** Several agents editing the same codebase in parallel tend to make conflicting decisions. Parallelize reading and research, and keep writing single-threaded.

## Trade-offs

- **Tokens.** Every worker re-reads its own instructions and sources. Budget for an order of magnitude more tokens than a single-agent run, and check that the task is worth it.
- **Debugging spreads out.** A bad answer could come from the plan, a worker, or the synthesis. Without a trace that links them ([Span-Level Tracing](../observability-and-evaluation/span-level-tracing.md)), you'll be guessing.
- **Latency.** Parallel workers cut wall-clock time, but planning and synthesis add two serial model calls, so short tasks get slower.

## Failure Modes

**Over-spawning.** Early versions of most orchestrators send 20 agents after a simple question. Put effort rules in the planner prompt (one agent for a fact lookup, a few for a comparison, more only for open-ended research) and back them with a hard `max_agents`. [Effort Scaling](../cost-and-efficiency/effort-scaling.md) covers this in detail.

**Overlap and gaps.** Two workers research the same thing under different wording, and nobody covers the third angle. Exclusions help. So does having the planner see previous objectives and never re-issue one.

**Context blow-up at synthesis.** Workers return everything they found and the orchestrator's context fills up at the final step, which is the most expensive place for that to happen. Enforce output budgets in code, not just in the prompt.

**No stopping rule.** The orchestrator keeps finding "one more gap". Cap rounds, and treat a malformed plan as "stop", not "retry".

## Implementation Example

An orchestrator with structured plans, parallel workers in fresh contexts, exclusions, per-worker output budgets, de-duplication and hard caps. The tests check the guard rails: caps, no re-spawning, truncation, and stopping on a malformed plan.

```bash
cd examples && pytest inference_and_serving/test_multi_agent_orchestration.py
```

<!-- example: examples/inference_and_serving/multi_agent_orchestration.py -->
```python
"""Multi-Agent Orchestration (orchestrator-worker, manager-as-tool).

The orchestrator plans, fans subtasks out to workers that each get a fresh,
narrow context, and synthesises their condensed results. The two things that
keep this from going wrong are explicit subtask boundaries and hard limits on
agents, rounds and how much each worker may send back.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

LLM = Callable[[str], str]

PLAN_PROMPT = """You are coordinating research on: {task}
Findings so far:
{findings}

Reply with JSON: {{"done": bool, "subtasks": [{{"objective": str, "exclude": str}}]}}.
Use at most {max_agents} subtasks. Each objective must not overlap the others.
Set done=true when the findings answer the task."""

WORKER_PROMPT = """Objective: {objective}
Out of scope (another agent covers it): {exclude}
Return only your key findings, at most {max_words} words."""


@dataclass
class Subtask:
    objective: str
    exclude: str = ""


@dataclass
class Orchestrator:
    planner: LLM  # the strong model: plans and synthesises
    worker: LLM  # often a cheaper model; runs with a fresh context per subtask
    max_agents: int = 4
    max_rounds: int = 3
    max_words_per_worker: int = 150
    trace: list[dict] = field(default_factory=list)

    def run(self, task: str) -> str:
        findings: dict[str, str] = {}
        for round_no in range(1, self.max_rounds + 1):
            plan = self._plan(task, findings)
            new = [s for s in plan["subtasks"] if s.objective not in findings][: self.max_agents]
            self.trace.append({"round": round_no, "done": plan["done"], "spawned": [s.objective for s in new]})
            if plan["done"] or not new:
                break
            with ThreadPoolExecutor(max_workers=len(new)) as pool:
                results = pool.map(self._delegate, new)
            for subtask, result in zip(new, results):
                findings[subtask.objective] = result

        notes = "\n".join(f"- {k}: {v}" for k, v in findings.items())
        return self.planner(f"Write the final answer to: {task}\nUsing these findings:\n{notes}")

    def _plan(self, task: str, findings: dict[str, str]) -> dict:
        raw = self.planner(
            PLAN_PROMPT.format(
                task=task,
                findings="\n".join(f"- {k}: {v}" for k, v in findings.items()) or "(none yet)",
                max_agents=self.max_agents,
            )
        )
        try:
            data = json.loads(raw)
            subtasks = [Subtask(s["objective"], s.get("exclude", "")) for s in data.get("subtasks", [])]
            return {"done": bool(data.get("done")), "subtasks": subtasks}
        except (json.JSONDecodeError, KeyError, TypeError):
            # A malformed plan ends the loop rather than spawning garbage work.
            return {"done": True, "subtasks": []}

    def _delegate(self, subtask: Subtask) -> str:
        reply = self.worker(
            WORKER_PROMPT.format(
                objective=subtask.objective, exclude=subtask.exclude or "nothing", max_words=self.max_words_per_worker
            )
        )
        # Enforce the budget even if the worker ignores the instruction:
        # the orchestrator's context is the scarce resource.
        return " ".join(reply.split()[: self.max_words_per_worker])
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Claude Agent SDK | Subagents with isolated contexts, driven by a lead agent |
| OpenAI Agents SDK | Both handoffs and agents-as-tools |
| LangGraph | Explicit graph and state; supervisor and swarm templates |
| AutoGen, CrewAI | Conversation-based and role-based multi-agent frameworks |

## Related Patterns

- [Effort Scaling](../cost-and-efficiency/effort-scaling.md) decides how many agents a task deserves.
- [Context Compaction](../cost-and-efficiency/context-compaction.md) keeps the orchestrator's own context under control across rounds.
- [Loop Termination](../loop-engineering/loop-termination.md): the round loop is still a loop and needs a stop condition.
- [Span-Level Tracing](../observability-and-evaluation/span-level-tracing.md) shows which worker produced the bad finding.

## Further Reading

- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system), Anthropic, 2025
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), Anthropic, 2024. Covers when *not* to use agents at all.
- [Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents), Cognition, 2025. The strongest counter-argument, and worth reading before you build.
- [AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation](https://arxiv.org/abs/2308.08155), Wu et al., 2023
