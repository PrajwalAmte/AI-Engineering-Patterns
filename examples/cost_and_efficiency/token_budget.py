"""Token Budget.

Split the context window into per-component budgets, reserve room for the
answer, and trim in a fixed order when something is over: least relevant
chunks first, then oldest conversation turns. Never silently cut the system
prompt or the user's question; if those alone don't fit, reject the request.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


class OverBudget(Exception):
    pass


@dataclass
class Budget:
    context_window: int = 32_000
    reserve_output: int = 2_000
    system: int = 2_000
    history: int = 6_000
    retrieved: int = 12_000
    user: int = 4_000


@dataclass
class Assembled:
    system: str
    history: list[str]
    chunks: list[str]
    user: str
    tokens: dict[str, int] = field(default_factory=dict)
    dropped: dict[str, int] = field(default_factory=dict)

    def prompt(self) -> str:
        return "\n\n".join([self.system, *self.history, *self.chunks, self.user])


def assemble(
    system: str,
    history: list[str],  # oldest first
    chunks: list[tuple[str, float]],  # (text, relevance)
    user: str,
    budget: Budget,
    count: Callable[[str], int],
) -> Assembled:
    total_in = budget.context_window - budget.reserve_output
    if count(system) > budget.system:
        raise OverBudget("system prompt exceeds its budget; fix the prompt, don't truncate it")
    if count(user) > budget.user:
        raise OverBudget("user input too long; ask the user to shorten it or attach it as a file")

    # Retrieved context: keep the most relevant chunks that fit.
    kept_chunks, used = [], 0
    for text, _ in sorted(chunks, key=lambda c: -c[1]):
        t = count(text)
        if used + t <= budget.retrieved:
            kept_chunks.append(text)
            used += t

    # History: keep the most recent turns that fit, in original order.
    kept_history, used_h = [], 0
    for turn in reversed(history):
        t = count(turn)
        if used_h + t > budget.history:
            break
        kept_history.insert(0, turn)
        used_h += t

    result = Assembled(system, kept_history, kept_chunks, user)
    result.tokens = {
        "system": count(system),
        "history": used_h,
        "retrieved": used,
        "user": count(user),
        "reserved_output": budget.reserve_output,
    }
    result.dropped = {"chunks": len(chunks) - len(kept_chunks), "turns": len(history) - len(kept_history)}
    if sum(v for k, v in result.tokens.items() if k != "reserved_output") > total_in:
        raise OverBudget("component budgets add up to more than the context window minus output reserve")
    return result
