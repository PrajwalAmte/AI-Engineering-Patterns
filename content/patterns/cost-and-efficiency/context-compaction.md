---
title: Context Compaction
pillar: cost-and-efficiency
status: validated-in-production
tags: [context-window, agents, summarization, tool-results]
related:
  - Token Budget
  - Sliding Context Window with Memory Consolidation
  - Multi-Agent Orchestration
  - Loop Termination
example: examples/cost_and_efficiency/context_compaction.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: When an agent's context nears the limit, clear old tool results first, and summarize older messages into a structured note only if that isn't enough.
sidebar:
  order: 3
---

## What It Is

Long-running agents accumulate context fast. Every file read, search result and command output stays in the message list. Compaction shrinks that list when it nears the window, in two stages:

1. **Clear old tool results.** Replace each with a one-line stub ("[cleared read_file result, 4,200 tokens]"). The agent already acted on them, and they're usually most of the tokens.
2. **Summarize, only if needed.** Turn the older messages into a structured note (goal, what's done, decisions, open items) and keep the most recent messages verbatim.

The user's original task is never compacted.

Coding agents and agent SDKs do this today (Claude Code's auto-compact, for example), which is why it's marked validated. The ordering (clear tool results first, then summarize) is the part most homegrown versions get wrong.

## The Problem It Solves

An agent fixing a bug reads ten files, runs the tests five times and greps the codebase. That's 80k tokens of tool output, most of it no longer relevant. Without compaction, it either hits the window limit and fails, or becomes slow and expensive on every later step, and less accurate as the important early instructions get buried.

Summarizing everything is the obvious fix and the wrong first move. It's slow (another model call), lossy, and it summarizes away recent reasoning the agent is still using.

## How It Works

<pre class="mermaid">
flowchart TD
    M["Message list"] --> C{"Over trigger<br/>(e.g. 80% of window)?"}
    C -->|"no"| K["Continue"]
    C -->|"yes"| S1["Stage 1: replace old tool results<br/>with one-line stubs, oldest first"]
    S1 --> D{"Under target<br/>(e.g. 50%)?"}
    D -->|"yes"| K
    D -->|"no"| S2["Stage 2: summarize older messages<br/>→ GOAL / DONE / DECISIONS / OPEN"]
    S2 --> N["[task] + [summary] + recent messages"]
    N --> K
</pre>

- **Trigger and target are different.** Compact at 80% and aim for 50%, so you aren't compacting again on the very next step.
- **Protect the tail.** The last few messages are what the agent is working on right now. Leave them alone.
- **Structure the summary.** Fixed headings make it much less likely that the summary drops the one constraint the user stated at the start.
- **Keep the task verbatim.** Summaries paraphrase. The user's exact words ("don't touch the public API") need to survive.

## When to Use It

- Agent loops with many tool calls: coding, research, data analysis, browser agents.
- Sessions that run longer than one context window.
- Rising per-step cost on long sessions, even when they fit.

## When NOT to Use It

- **Short tasks** that finish well inside the window.
- **Tasks where exact earlier output matters later** (diffing two large tool outputs, legal text). Store those outside the context and re-fetch them, instead of compacting.
- **Conversational chat.** [Sliding Context Window with Memory Consolidation](../retrieval-and-memory/sliding-context-window.md) fits dialogue better: it pins user facts and keeps a rolling window.

## Trade-offs

- **Clearing tool results is cheap but blind.** If the agent needs that file again, it must re-read it, which costs one more tool call. That's usually a good trade.
- **Summaries cost a model call and lose detail.** That's why they're stage 2.
- **Seams in reasoning.** After compaction, the agent occasionally redoes work it already did, because the summary didn't make clear it was finished. A "DONE" section with concrete identifiers (file names, test names) helps.

## Failure Modes

**The constraint that got summarized away.** The user said "don't change the database schema" at step 1, and the summary at step 40 says "fix the failing test". Keep the task verbatim and give the summary a GOAL section that copies constraints word for word.

**Compaction loops.** A trigger close to the target means compacting every step, paying for a summary each time. Keep a wide gap between them.

**Clearing the result the agent is using.** An aggressive stage 1 clears the tool output from two steps ago that the agent is about to quote. Protect a recent tail of messages.

## Implementation Example

Trigger and target thresholds, a protected recent tail, stage 1 stubbing of tool results (oldest first, stopping as soon as the target is reached), and stage 2 structured summarization that keeps the task message verbatim.

```bash
cd examples && pytest cost_and_efficiency/test_context_compaction.py
```

<!-- example: examples/cost_and_efficiency/context_compaction.py -->
```python
"""Context Compaction (for agent loops).

When an agent's message list nears the window, compact it in two stages:

1. Clear old tool results. They are usually the bulk of the tokens and the
   agent already acted on them; a one-line stub keeps the trail.
2. Only if that isn't enough, summarise older messages into a structured
   note (goal, decisions, state, open items) and keep the recent ones as-is.

The first user message (the task) is always kept verbatim.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

SUMMARY_PROMPT = """Summarise this agent transcript for the agent itself to continue the task.
Use these headings exactly:
GOAL: the user's goal and constraints, verbatim where possible
DONE: what has been completed, with file names / ids / numbers
DECISIONS: choices made and why
OPEN: what is left, including errors not yet resolved

{transcript}"""


@dataclass
class Message:
    role: str  # "user" | "assistant" | "tool"
    content: str
    name: str = ""  # tool name for tool messages


@dataclass
class Compactor:
    summarize: Callable[[str], str]
    count: Callable[[str], int]
    window: int = 100_000
    trigger: float = 0.8  # compact when over 80% of the window
    target: float = 0.5  # aim to get back under 50%
    keep_recent: int = 6  # messages never touched
    log: list[str] = field(default_factory=list)

    def tokens(self, messages: list[Message]) -> int:
        return sum(self.count(m.content) for m in messages)

    def maybe_compact(self, messages: list[Message]) -> list[Message]:
        if self.tokens(messages) <= self.window * self.trigger:
            return messages

        # Stage 1: stub out old tool results, oldest first.
        out = list(messages)
        protected = len(out) - self.keep_recent
        for i in range(1, max(protected, 1)):
            if out[i].role == "tool" and not out[i].content.startswith("[cleared"):
                size = self.count(out[i].content)
                out[i] = Message("tool", f"[cleared {out[i].name} result, {size} tokens]", out[i].name)
                if self.tokens(out) <= self.window * self.target:
                    self.log.append("cleared tool results")
                    return out

        # Stage 2: summarise everything between the task and the recent tail.
        task, middle, recent = out[0], out[1:protected], out[max(protected, 1):]
        if not middle:
            return out
        transcript = "\n".join(f"{m.role}{f'({m.name})' if m.name else ''}: {m.content}" for m in middle)
        note = self.summarize(SUMMARY_PROMPT.format(transcript=transcript))
        self.log.append(f"summarised {len(middle)} messages")
        return [task, Message("user", f"[Summary of earlier work]\n{note}"), *recent]
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Claude Code `/compact` and auto-compact | Reference behavior for coding agents |
| Anthropic context editing / tool-result clearing | API-level clearing of old tool results |
| OpenAI Agents SDK sessions | Session memory with trimming and summarization hooks |
| LangGraph | Message-trimming and summarization nodes in agent graphs |

## Related Patterns

- [Token Budget](token-budget.md) sets the window and the thresholds.
- [Sliding Context Window with Memory Consolidation](../retrieval-and-memory/sliding-context-window.md) is the conversational counterpart.
- [Multi-Agent Orchestration](../inference-and-serving/multi-agent-orchestration.md) is another way out: give subtasks fresh contexts instead of compacting one long one.
- [Loop Termination](../loop-engineering/loop-termination.md): long loops are where compaction is needed, and they also need a stop rule.

## Further Reading

- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), Anthropic, 2025
- [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560), Packer et al., 2023
- [Lost in the Middle](https://arxiv.org/abs/2307.03172), Liu et al., 2023
