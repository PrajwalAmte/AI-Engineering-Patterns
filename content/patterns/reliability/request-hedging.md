---
title: Request Hedging for LLMs
pillar: reliability
status: emerging
tags: [reliability, latency, tail-latency, redundancy]
related:
  - Circuit Breaker for LLMs
  - LLM Gateway
  - Uncertainty-Triggered Retry
example: examples/reliability/request_hedging.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: If the primary hasn't answered by its own p95, send the same request to a backup and take whichever good answer arrives first.
sidebar:
  order: 2
---

## What It Is

Hedged requests come from Google's *The Tail at Scale*. Send a request to the primary. If it hasn't answered by roughly its 95th-percentile latency, send the same request to a second replica, use whichever answer arrives first, and cancel the other.

For LLMs, the "second replica" is usually another provider or region serving a comparable model. One twist: "first" has to mean first *acceptable* answer, because a fast empty completion is not a win.

## The Problem It Solves

LLM latency has a long tail. Most requests to a given model finish in a few seconds, but a small share sit in a provider's queue, land on a cold or overloaded replica, or stall partway through the stream. Users never complain about the median. They remember the time the assistant spun for 30 seconds.

A timeout-and-retry approach makes the slow requests slower still: you wait out the timeout, *then* start again. Hedging starts the second attempt while the first is still running, so the user waits for whichever finishes first.

## How It Works

<pre class="mermaid">
sequenceDiagram
    participant C as Client
    participant P as Primary
    participant B as Backup
    C->>P: request (t=0)
    Note over C: wait up to hedge delay<br/>(primary's rolling p95)
    alt primary answers in time
        P-->>C: answer
    else delay passes
        C->>B: same request (hedge)
        alt backup first and acceptable
            B-->>C: answer
            C-xP: cancel
        else primary first and acceptable
            P-->>C: answer
            C-xB: cancel
        end
    end
</pre>

1. **Send to the primary.**
2. **Wait up to the hedge delay.** Derive it from the primary's own recent latencies (p90–p95), not a hard-coded number, so it follows the provider as it speeds up or slows down.
3. **Hedge** by sending the identical request to the backup.
4. **Race,** and accept the first answer that passes a cheap check (non-empty, valid JSON if JSON was requested). A primary that answers fast but badly also triggers the hedge.
5. **Cancel the loser.** With streaming APIs, closing the connection stops generation, and most providers then stop charging for output tokens.

At a p95 delay, only about 5% of requests ever hedge, so the extra cost is a few percent of spend, not double.

## When to Use It

- Interactive features with a latency SLO, where p99 is the number that matters.
- You have a second provider or region with comparable quality.
- The request has no side effects: plain generation, classification, extraction.

## When NOT to Use It

- **Anything with side effects.** Never hedge a tool call that sends an email, writes to a database or charges a card. You'd do it twice.
- **Batch and background jobs.** Nobody is waiting, so the extra cost buys nothing.
- **The backup is noticeably worse.** Hedging then serves your worst answers to exactly the users who already waited longest.
- **Cancellation doesn't stop billing** on your provider or proxy. Then every hedge costs a full second request. Test this before you rely on it.

## Trade-offs

- **Cost.** You pay for duplicate work on the hedged fraction of requests. The hedge delay is the dial between cost and tail latency.
- **Inconsistent answers.** The same question can be answered by different models depending on timing. If outputs need to be consistent (same JSON shape, same tone), check that both providers produce them.
- **Lopsided backup traffic.** The backup only ever sees your slowest requests, and their volume tracks the primary's bad days. Size its rate limits for that.

## Failure Modes

**The delay is too short, so most requests hedge.** A hard-coded 1-second delay against a provider whose median is 2 seconds hedges most requests and roughly doubles spend. Use a rolling percentile, and alert if the hedge rate goes above about 10%.

**Primary outage floods the backup.** The primary degrades for an hour, every request hedges, and the backup hits its rate limit. Now both paths fail. When the hedge rate spikes, the [circuit breaker](circuit-breaker.md) should open and send traffic to the backup directly, without the duplicate.

**Cancellation doesn't propagate.** A proxy between you and the provider keeps the upstream connection open after you cancel, so you pay for both. Check on the provider's usage dashboard, not just in your client logs.

## Implementation Example

An asyncio hedge with a rolling-p95 delay, an acceptance check, hedging when the primary returns a bad fast answer, and cancellation of the loser. The tests use real (tiny) sleeps to race the providers, including one that checks the slow primary was actually cancelled.

```bash
cd examples && pytest reliability/test_request_hedging.py
```

<!-- example: examples/reliability/request_hedging.py -->
```python
"""Request Hedging for LLMs.

Send to the primary. If it hasn't answered by the hedge delay (set from its
own recent p95), send the same request to a backup and take whichever
*acceptable* answer arrives first. Cancel the loser.

Only for requests without side effects: never hedge a tool call that writes.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

AsyncLLM = Callable[[str], Awaitable[str]]


class LatencyTracker:
    """Rolling window of observed latencies; the hedge delay follows the provider."""

    def __init__(self, window: int = 200, quantile: float = 0.95, default_s: float = 2.0, min_samples: int = 20):
        self.samples: deque[float] = deque(maxlen=window)
        self.quantile, self.default_s, self.min_samples = quantile, default_s, min_samples

    def observe(self, seconds: float) -> None:
        self.samples.append(seconds)

    def delay(self) -> float:
        if len(self.samples) < self.min_samples:
            return self.default_s
        ordered = sorted(self.samples)
        return ordered[min(int(len(ordered) * self.quantile), len(ordered) - 1)]


@dataclass
class HedgeResult:
    text: str
    winner: str
    hedged: bool
    latency_s: float


async def hedged_complete(
    prompt: str,
    primary: tuple[str, AsyncLLM],
    backup: tuple[str, AsyncLLM],
    tracker: LatencyTracker,
    accept: Callable[[str], bool] = lambda text: bool(text.strip()),
) -> HedgeResult:
    start = time.monotonic()
    names: dict[asyncio.Task, str] = {}

    def launch(name: str, call: AsyncLLM) -> None:
        names[asyncio.ensure_future(call(prompt))] = name

    launch(*primary)
    pending = set(names)
    done, pending = await asyncio.wait(pending, timeout=tracker.delay())
    hedged = False
    if not done:
        hedged = True
        launch(*backup)
        pending = set(names) - done

    try:
        while True:
            for task in done:
                if task.exception() is None and accept(task.result()):
                    elapsed = time.monotonic() - start
                    if names[task] == primary[0]:
                        tracker.observe(elapsed)
                    return HedgeResult(task.result(), names[task], hedged, elapsed)
            if not hedged:
                # Primary answered fast but badly: that's a reason to try the backup too.
                hedged = True
                launch(*backup)
                pending = set(names) - done
            if not pending:
                raise RuntimeError("no provider returned an acceptable answer")
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in pending:
            task.cancel()  # with streaming APIs, closing the connection stops billing
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Custom (asyncio, Go contexts, …) | Most teams write this themselves. It's small, and the policy is yours |
| LiteLLM, Portkey | Timeouts plus fallbacks: sequential, not hedged, but a reasonable starting point |
| gRPC hedging policy | Built-in hedging if you self-host models behind gRPC |

## Related Patterns

- [Circuit Breaker for LLMs](circuit-breaker.md) handles sustained degradation. Hedging handles individual slow requests. Use the breaker to stop hedging against a provider that is down.
- [LLM Gateway](../inference-and-serving/llm-gateway.md) is the natural place to implement hedging, since it already sees every provider's latency.
- [Uncertainty-Triggered Retry](uncertainty-triggered-retry.md) re-runs answers that are *bad*. Hedging races answers that are *slow*.

## Further Reading

- [The Tail at Scale](https://research.google/pubs/the-tail-at-scale/), Jeffrey Dean and Luiz André Barroso, CACM 2013
- [gRPC request hedging design (A6)](https://github.com/grpc/proposal/blob/master/A6-client-retries.md)
