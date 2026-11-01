"""Cascading Context Assembly.

Answer with a little context first. Only if the model says it can't answer
from that, retrieve more and try again. Most questions stop at the first
tier; the few that need everything still get it.

The model is asked to reply with an exact sentinel when the context is
insufficient, which is far more reliable to detect than hedging language.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

INSUFFICIENT = "INSUFFICIENT_CONTEXT"

PROMPT = """Answer the question using only the context below.
If the context does not contain the answer, reply with exactly {sentinel} and nothing else.

Context:
{context}

Question: {question}"""


@dataclass
class Tier:
    k: int  # chunks to retrieve
    llm: Callable[[str], str]  # the last tier often uses a stronger model


@dataclass
class Result:
    answer: str
    tier: int  # 0-based index of the tier that answered
    chunks_used: int
    calls: int


def answer(
    question: str,
    retrieve: Callable[[str, int], list[str]],  # (query, k) -> chunks, best first
    tiers: list[Tier],
) -> Result:
    for i, tier in enumerate(tiers):
        chunks = retrieve(question, tier.k)
        reply = tier.llm(PROMPT.format(sentinel=INSUFFICIENT, context="\n---\n".join(chunks), question=question))
        if INSUFFICIENT not in reply:
            return Result(reply.strip(), i, len(chunks), i + 1)
    # Even the widest tier couldn't answer: say so rather than letting the model guess.
    return Result("I couldn't find that in the available documents.", len(tiers) - 1, len(chunks), len(tiers))
