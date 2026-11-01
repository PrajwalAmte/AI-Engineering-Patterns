---
title: Sliding Context Window with Memory Consolidation
pillar: retrieval-and-memory
status: validated-in-production
tags: [memory, conversation, context-management, summarization]
related:
  - Context Compaction
  - Cascading Context Assembly
  - Token Budget
example: examples/retrieval_and_memory/sliding_context_window.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Keep recent turns word for word, summarize older ones, and pin the facts that must never be summarized away.
sidebar:
  order: 4
---

## What It Is

A memory layout for long conversations, with three zones:

- **Pinned facts**: things the user said that must survive any amount of compression ("I'm allergic to peanuts", "the deadline is Friday").
- **Archive**: summaries of older turns.
- **Verbatim window**: the most recent turns, kept exactly as they were said.

When the verbatim window exceeds its token budget, the oldest turns are summarized into the archive. When the archive exceeds *its* budget, it is summarized again. Almost every production chat product uses some version of this, and this page describes the version with pinning, which is the part most often left out.

## The Problem It Solves

There are two naive approaches, and both break.

**Truncating old turns** gives the assistant amnesia. Forty turns into a support conversation it asks for the order number the user gave in turn two.

**Summarizing everything** loses the detail of the last few turns, which is what "as I just said" refers to. It also loses the specific things users care about. A summarizer asked to keep "the important parts" will reduce "allergic to peanuts" to "has dietary preferences".

## How It Works

<pre class="mermaid">
flowchart TD
    T["New turn"] --> P{"User stating a must-keep fact?"}
    P -->|"yes"| PIN["Add to pinned"]
    P --> V["Append to verbatim window"]
    PIN --> V
    V --> O{"Verbatim > budget?"}
    O -->|"yes"| C["Summarize oldest batch → archive<br/>(always keep the last exchange)"]
    O -->|"no"| B
    C --> A{"Archive > budget?"}
    A -->|"yes"| R["Summarize the archive itself"]
    A -->|"no"| B["Build context:<br/>system + pinned + archive + verbatim"]
    R --> B
</pre>

1. **Pin.** Detect must-keep statements. The example uses a keyword regex. Production systems often have the model call a `remember(fact)` tool, or let the user say "remember this".
2. **Append** the turn to the verbatim window.
3. **Consolidate** when the window is over budget. Summarize the oldest few turns with a prompt that names exactly what to keep: decisions, constraints, numbers, names, open questions.
4. **Re-consolidate** when the archive itself grows too big. Summarizing summaries loses detail every time, which is exactly why pinned facts sit outside the archive.
5. **Assemble** the context in a fixed order: system prompt, pinned facts, archive, verbatim turns.

## When to Use It

- Conversations regularly run past what fits comfortably in context, or past what you want to pay for on every turn.
- Facts from early in the conversation matter later (support, tutoring, sales, planning).
- You need a predictable cost per turn regardless of conversation length.

## When NOT to Use It

- **Short or transactional chats.** If conversations rarely go past ten turns, keep everything.
- **The context window is large and cost isn't an issue.** Long-context models make "keep everything" viable for longer than it used to be, though quality still drops when the important detail is buried in the middle.
- **Cross-session memory.** That needs a store you search (a profile or a vector memory). This pattern manages one session's context.

## Trade-offs

- **Summaries lose information, by design.** The consolidation prompt decides what survives. Treat it as product code: version it and evaluate it.
- **Consolidation costs a model call** and adds latency on the turns where it runs. Running it in the background after responding hides the latency but needs care with concurrent turns.
- **Seams can show.** The user quotes their own exact words from 30 turns ago, and the model has only a paraphrase. That's mostly harmless, but the model shouldn't claim the user never said it.

## Failure Modes

**The one fact that mattered gets summarized away.** This is the failure users notice most ("I already told you!"). Pinning is the fix. Summarizer prompt tweaks alone won't solve it.

**Uneven latency.** Synchronous consolidation makes every tenth turn a few seconds slower, and users read that as the product hanging. Respond first and consolidate afterwards, locking the conversation so two consolidations can't race.

**The archive keeps growing.** After a hundred turns, the archive alone fills the budget. Re-consolidate it hierarchically, or move old archive entries to a searchable store and retrieve them only when relevant.

## Implementation Example

The three zones with pinning, batch consolidation of the oldest turns, re-consolidation of the archive, and a guarantee that the latest exchange is never summarized. The token counter is injectable so the tests can use exact word counts.

```bash
cd examples && pytest retrieval_and_memory/test_sliding_context_window.py
```

<!-- example: examples/retrieval_and_memory/sliding_context_window.py -->
```python
"""Sliding Context Window with Memory Consolidation.

Three zones: pinned facts (never compressed), a consolidated archive of older
turns, and the most recent turns verbatim. When the verbatim zone outgrows its
budget, the oldest turns are summarised into the archive. When the archive
outgrows *its* budget, it is summarised again.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

CONSOLIDATE_PROMPT = """Summarise this conversation fragment as short bullet points.
Keep every decision, constraint, preference, number, name and open question.
Drop greetings and small talk.

{fragment}"""

# Things users say that must survive any amount of summarisation.
PIN_HINTS = re.compile(r"\b(remember|always|never|allergic|my name is|don't ever|deadline)\b", re.I)


@dataclass
class Turn:
    role: str
    text: str


@dataclass
class ConversationMemory:
    summarize: Callable[[str], str]
    count_tokens: Callable[[str], int] = lambda s: max(1, len(s) // 4)
    verbatim_budget: int = 3000
    archive_budget: int = 1500
    consolidate_batch: int = 4  # turns moved to the archive at a time
    pinned: list[str] = field(default_factory=list)
    archive: list[str] = field(default_factory=list)
    verbatim: list[Turn] = field(default_factory=list)

    def add(self, role: str, text: str) -> None:
        if role == "user" and PIN_HINTS.search(text):
            self.pinned.append(text)
        self.verbatim.append(Turn(role, text))
        self._maybe_consolidate()

    def context(self, system_prompt: str) -> str:
        parts = [system_prompt]
        if self.pinned:
            parts.append("Things the user asked you to keep in mind:\n" + "\n".join(f"- {p}" for p in self.pinned))
        if self.archive:
            parts.append("Earlier in this conversation:\n" + "\n".join(self.archive))
        parts.append("\n".join(f"{t.role}: {t.text}" for t in self.verbatim))
        return "\n\n".join(parts)

    def _tokens(self, texts: list[str]) -> int:
        return sum(self.count_tokens(t) for t in texts)

    def _maybe_consolidate(self) -> None:
        # Always keep at least one exchange verbatim, however long it is.
        while self._tokens([t.text for t in self.verbatim]) > self.verbatim_budget and len(self.verbatim) > 2:
            batch = self.verbatim[: min(self.consolidate_batch, len(self.verbatim) - 2)]
            self.verbatim = self.verbatim[len(batch):]
            fragment = "\n".join(f"{t.role}: {t.text}" for t in batch)
            self.archive.append(self.summarize(CONSOLIDATE_PROMPT.format(fragment=fragment)))

        if self._tokens(self.archive) > self.archive_budget and len(self.archive) > 1:
            merged = self.summarize(CONSOLIDATE_PROMPT.format(fragment="\n".join(self.archive)))
            self.archive = [merged]
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| LangChain / LangGraph memory | Summary-buffer memory: a recent-turns window plus a running summary |
| LlamaIndex ChatMemoryBuffer | Token-limited window; add your own consolidation |
| Mem0, Zep, Letta (MemGPT) | Long-term memory services: extract facts and retrieve them across sessions |
| Claude Code, ChatGPT and similar | Auto-compaction of long sessions; good reference behavior to study |

## Related Patterns

- [Context Compaction](../cost-and-efficiency/context-compaction.md) is the general technique. This pattern applies it to conversation turns.
- [Cascading Context Assembly](../cost-and-efficiency/cascading-context-assembly.md) decides what else goes into the context next to the conversation.
- [Token Budget](../cost-and-efficiency/token-budget.md) sets the numbers this pattern stays within.

## Further Reading

- [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560), Packer et al., 2023
- [Lost in the Middle: How Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172), Liu et al., 2023. Why "just keep everything" has limits.
- [Recursively Summarizing Books with Human Feedback](https://arxiv.org/abs/2109.10862), Wu et al. (OpenAI), 2021. Hierarchical summarization.
