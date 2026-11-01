---
title: Circuit Breaker for LLMs
pillar: reliability
status: validated-in-production
tags: [reliability, resilience, fallback, latency]
related:
  - LLM Gateway
  - Request Hedging for LLMs
  - Model Router
example: examples/reliability/circuit_breaker.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Stop sending traffic to a degraded provider before your users notice, and count slow or empty answers as failures, not just errors.
sidebar:
  order: 1
---

## What It Is

The classic circuit breaker from Michael Nygard's *Release It!*, adjusted for one awkward fact about LLM providers: they rarely go down cleanly. The breaker watches recent calls to a provider. When too many of them fail, it "opens" and sends everything to a fallback for a while. After a cooldown it lets a few probe requests through, and closes again if they succeed.

The LLM-specific part is the definition of "failure". An exception is a failure. So is a completion that took 40 seconds, and so is an empty string returned with a 200 OK.

## The Problem It Solves

When a provider has a bad hour, it usually doesn't refuse connections. Latency drifts from 2 seconds to 20. Some completions come back empty or cut off halfway. Rate-limit errors show up for a few percent of requests. Your HTTP health check stays green throughout.

Without a breaker, every request keeps paying that cost until someone sees the latency graph and flips a feature flag by hand. Plain retry logic makes things worse: it multiplies load on a provider that is already struggling and stretches each user's wait.

## How It Works

<pre class="mermaid">
flowchart LR
    C["Closed<br/>normal traffic"] -->|"failure rate ≥ threshold<br/>over at least min_calls"| O["Open<br/>everything goes to fallback"]
    O -->|"cooldown elapsed"| H["Half-open<br/>let probes through"]
    H -->|"N probes succeed"| C
    H -->|"any probe fails"| O
</pre>

1. **Closed.** Calls go to the primary. Each result (ok or failed) goes into a sliding window of the last `window` calls.
2. **Trip.** Once the window holds at least `min_calls` results and the failure rate reaches `failure_threshold`, the breaker opens. The `min_calls` floor stops three unlucky requests at 3 a.m. from tripping it.
3. **Open.** The primary is not called at all. Requests go straight to the fallback, so users pay no timeout tax.
4. **Half-open.** After `cooldown_s`, requests are let through as probes. `probes_to_close` successes in a row close the breaker. One failure reopens it and restarts the cooldown.

A call counts as failed if it raises, returns nothing usable, or takes longer than the latency budget. A slow answer is still returned to the user, since they have already waited for it, but it counts against the provider.

## When to Use It

- You have somewhere else to send traffic: a second provider, a smaller model, or a cached or templated answer.
- Provider degradation has already caused an incident, or would be expensive if it did.
- Each instance handles enough traffic (tens of requests per minute or more) for a failure rate to mean something.

## When NOT to Use It

- **You have no fallback.** A breaker with nowhere to route only fails faster. That can still protect downstream systems, but it won't keep the product working.
- **Traffic is very low.** With a handful of requests per minute, the window is mostly noise. Use per-request retries with a deadline instead.
- **The primary and fallback share a backend.** Two SKUs served by the same underlying model will degrade together, so failing over between them buys nothing.

## Trade-offs

- **False trips are expensive.** Each trip moves users to a weaker or more expensive model for the whole cooldown. `min_calls` and the threshold are the knobs, and you should tune them against real incident data rather than guesses.
- **Recovery lags.** The breaker can't know the provider has recovered until the cooldown ends. A shorter cooldown means more probe failures during long outages.
- **The breaker adds state to the hot path.** In a fleet of gateway instances, you choose between a shared breaker (Redis or similar, which adds another dependency) and per-instance breakers (simpler, but each one needs enough traffic to decide on its own).

## Failure Modes

**Fallback stampede.** The primary trips and 100% of traffic lands on a fallback that was sized for 10%. Now the fallback rate-limits too, and you have two unhealthy paths instead of one. Load-test the fallback at full volume, or shed load (queue, degrade, or return a cached answer) instead of moving all traffic at once.

**Tripping on your own bugs.** A bad prompt deploy that makes the model return empty JSON looks exactly like provider degradation. The breaker opens, the fallback gets the same bad prompt, and the dashboards blame the vendor. Log *why* each call failed, and alert separately when the fallback's failure rate rises too.

**Split brain across instances.** With per-instance breakers, half your pods may be on the fallback while the other half aren't. That's fine as long as you know about it. Export breaker state as a metric so the on-call engineer isn't left guessing.

## Implementation Example

The code below is the full example from the repo, and it runs in CI on every push. The clock is injectable so the tests can step through cooldowns without sleeping. Swap `primary` and `fallback` for your real clients.

```bash
cd examples && pytest reliability/test_circuit_breaker.py
```

<!-- example: examples/reliability/circuit_breaker.py -->
```python
"""Circuit Breaker for LLMs.

Counts slow and empty completions as failures, not just exceptions, because
LLM providers usually degrade with a 200 OK.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from enum import Enum


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: float = 0.5,  # trip when half the window failed...
        window: int = 20,
        min_calls: int = 10,  # ...but never on fewer than this many calls
        cooldown_s: float = 30.0,
        probes_to_close: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.failure_threshold = failure_threshold
        self.min_calls = min_calls
        self.cooldown_s = cooldown_s
        self.probes_to_close = probes_to_close
        self._clock = clock
        self._results: deque[bool] = deque(maxlen=window)
        self._state = State.CLOSED
        self._opened_at = 0.0
        self._probe_successes = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> State:
        with self._lock:
            return self._current_state()

    def allow(self) -> bool:
        return self.state is not State.OPEN

    def record(self, ok: bool) -> None:
        with self._lock:
            if self._current_state() is State.HALF_OPEN:
                if not ok:
                    self._trip()
                    return
                self._probe_successes += 1
                if self._probe_successes >= self.probes_to_close:
                    self._state = State.CLOSED
                    self._results.clear()
                return

            self._results.append(ok)
            if len(self._results) >= self.min_calls:
                failure_rate = self._results.count(False) / len(self._results)
                if failure_rate >= self.failure_threshold:
                    self._trip()

    def _current_state(self) -> State:
        if self._state is State.OPEN and self._clock() - self._opened_at >= self.cooldown_s:
            self._state = State.HALF_OPEN
            self._probe_successes = 0
        return self._state

    def _trip(self) -> None:
        self._state = State.OPEN
        self._opened_at = self._clock()
        self._results.clear()


def complete(
    prompt: str,
    primary: Callable[[str], str],
    fallback: Callable[[str], str],
    breaker: CircuitBreaker,
    latency_budget_s: float = 10.0,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[str, str]:
    """Returns (text, which_provider_answered)."""
    if breaker.allow():
        start = clock()
        try:
            text = primary(prompt)
        except Exception:
            breaker.record(False)
        else:
            usable = bool(text.strip())
            breaker.record(usable and clock() - start <= latency_budget_s)
            # A slow answer still counts against the provider, but the user
            # already waited for it, so hand it back rather than waiting twice.
            if usable:
                return text, "primary"
    return fallback(prompt), "fallback"
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| LiteLLM Router | Per-deployment cooldowns after repeated failures; config-driven fallbacks |
| Portkey, Kong AI Gateway | Gateway-level fallbacks and retries across providers |
| Resilience4j, Polly | General-purpose breakers (JVM, .NET). You define what counts as a failure |
| Envoy outlier detection | Ejects unhealthy upstream hosts; works if you self-host models behind it |

Most off-the-shelf breakers count only errors. If latency and empty output matter to you, and for LLMs they should, check whether the tool lets you report a call as failed yourself.

## Related Patterns

- [LLM Gateway](../inference-and-serving/llm-gateway.md) is the natural home for the breaker, because every call already passes through it.
- [Request Hedging for LLMs](request-hedging.md) attacks tail latency per request. The breaker reacts to sustained degradation. They work well together.
- [Model Router](../inference-and-serving/model-router.md) decides where traffic *should* go. The breaker overrides that when the chosen route is unhealthy.

## Further Reading

- [CircuitBreaker](https://martinfowler.com/bliki/CircuitBreaker.html), Martin Fowler
- [Release It!, 2nd edition](https://pragprog.com/titles/mnee2/release-it-second-edition/), Michael Nygard. The original source of the pattern.
- [LiteLLM routing and fallbacks](https://docs.litellm.ai/docs/routing)
