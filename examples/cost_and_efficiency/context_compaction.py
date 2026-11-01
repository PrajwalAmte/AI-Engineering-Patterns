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
