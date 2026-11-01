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
