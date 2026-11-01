"""Span-Level Tracing.

One trace per request, one span per pipeline step, with tokens and cost on the
model spans. Parent/child links come from a context variable, so nested and
async steps attach to the right parent without passing span objects around.

In production use OpenTelemetry with the GenAI semantic conventions; this is
the same shape with no dependencies, so you can see what the SDK is doing.
"""

from __future__ import annotations

import contextvars
import hashlib
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

# Span *names* must come from a fixed set. Put variable things (user id, query)
# in attributes; a span name per query makes every dashboard useless.
SPAN_NAMES = {"request", "retrieve", "embed", "vector_search", "rerank", "build_prompt", "llm", "tool", "guardrail"}
SENSITIVE_ATTRS = {"prompt", "completion", "query", "user_input"}


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_id: str | None
    name: str
    start: float
    end: float = 0.0
    attributes: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def duration_s(self) -> float:
        return self.end - self.start


_current: contextvars.ContextVar[Span | None] = contextvars.ContextVar("current_span", default=None)


class Tracer:
    def __init__(self, clock: Callable[[], float] = time.monotonic, keep_raw_text: bool = False):
        self.clock = clock
        self.keep_raw_text = keep_raw_text  # off by default: traces get shipped to third parties
        self.finished: list[Span] = []

    @contextmanager
    def span(self, name: str, **attributes) -> Iterator[Span]:
        if name not in SPAN_NAMES:
            raise ValueError(f"unknown span name {name!r}; add it to SPAN_NAMES deliberately")
        parent = _current.get()
        span = Span(
            trace_id=parent.trace_id if parent else uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            parent_id=parent.span_id if parent else None,
            name=name,
            start=self.clock(),
        )
        self.set(span, **attributes)
        token = _current.set(span)
        try:
            yield span
        except Exception as exc:
            span.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            span.end = self.clock()
            _current.reset(token)
            self.finished.append(span)

    def set(self, span: Span, **attributes) -> None:
        for key, value in attributes.items():
            if key in SENSITIVE_ATTRS and not self.keep_raw_text:
                text = str(value)
                span.attributes[f"{key}.sha256"] = hashlib.sha256(text.encode()).hexdigest()[:16]
                span.attributes[f"{key}.chars"] = len(text)
            else:
                span.attributes[key] = value

    # ---- the questions you actually ask of traces ----

    def tree(self, trace_id: str) -> list[tuple[int, Span]]:
        spans = [s for s in self.finished if s.trace_id == trace_id]
        children = defaultdict(list)
        for s in spans:
            children[s.parent_id].append(s)
        out: list[tuple[int, Span]] = []

        def walk(parent_id, depth):
            for s in sorted(children[parent_id], key=lambda s: s.start):
                out.append((depth, s))
                walk(s.span_id, depth + 1)

        walk(None, 0)
        return out

    def rollup(self) -> dict[str, dict[str, float]]:
        """Total time, tokens and cost per span name, across all traces."""
        totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for s in self.finished:
            t = totals[s.name]
            t["count"] += 1
            t["seconds"] += s.duration_s
            t["tokens"] += s.attributes.get("input_tokens", 0) + s.attributes.get("output_tokens", 0)
            t["cost_usd"] += s.attributes.get("cost_usd", 0.0)
            t["errors"] += 1 if s.error else 0
        return {k: dict(v) for k, v in totals.items()}
