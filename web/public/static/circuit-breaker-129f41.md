---
title: Circuit Breaker for LLMs
pillar: reliability
status: validated-in-production
tags: [reliability, resilience, fallback, monitoring]
related:
  - Fallback Chain
  - Graceful Degradation Pattern
  - Health Check Pattern
  - LLM Gateway Pattern
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Detect LLM provider degradation early and trip to fallback before user impact accumulates.
sidebar:
  order: 1
---

## What It Is

A circuit breaker for LLMs monitors the failure rate, latency, and quality of LLM provider responses. When degradation exceeds a threshold, the circuit "opens" and stops sending requests to the failing provider, redirecting traffic to a fallback. After a cooldown period, the circuit enters a "half-open" state to probe whether the provider has recovered.

## The Problem It Solves

LLM providers degrade in ways that traditional health checks miss. A provider can return HTTP 200 while delivering:

- Responses 5x slower than normal.
- Empty or truncated completions.
- Content filter rejections on legitimate queries.
- Repetitive, low-quality outputs due to backend issues.

Without a circuit breaker, your system continues sending requests to a degraded provider, accumulating user-facing failures until someone notices manually. Standard HTTP retry logic makes this worse by adding load to an already struggling provider.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Closed state: normal traffic"] -->|"Failure rate breaches threshold"| B["Open state: fail fast"]
    B --> C["Route traffic to fallback provider"]
    B -->|"Cooldown expires"| D["Half-open state: send probe requests"]
    D -->|"Probes pass"| A
    D -->|"Probes fail"| B
</pre>

1. **Closed state**: Requests flow normally. The breaker tracks failures (errors, timeouts, latency threshold violations) in a sliding window.
2. **Trip condition**: When failures in the window exceed the threshold (e.g., 50% failure rate over last 20 requests), the circuit opens.
3. **Open state**: All requests are immediately redirected to the fallback provider. No requests reach the failing provider.
4. **Cooldown**: After a configured cooldown period (e.g., 30-60 seconds), the circuit moves to half-open.
5. **Half-open state**: A limited number of probe requests are sent to the original provider. If they succeed, the circuit closes. If they fail, it re-opens.

For LLMs specifically, the failure definition must include latency breaches and quality degradation, not just HTTP errors.

## When to Use It

- Your system has at least one fallback provider or model.
- Provider outages or degradation have caused production incidents.
- You need to protect user experience during provider issues.
- Your system makes enough requests to detect degradation statistically (at least tens of requests per minute).

## When not to Use It

- You have only one LLM provider with no fallback. A circuit breaker without a fallback just fails faster — useful for protecting downstream systems from cascading failures, but not for maintaining service.
- Your request volume is too low to detect degradation reliably (fewer than 10 requests per minute). The sliding window will produce noisy signals.
- All providers share the same backend (e.g., two products both calling the same underlying model). Failing over will not help.

## Trade-offs

1. **Flash trips** — A short burst of errors can trip the circuit unnecessarily, routing traffic away from a healthy provider. Tuning the window size and threshold is critical.
2. **Fallback quality** — The fallback model is typically weaker or more expensive. Unnecessary trips degrade quality or increase cost.
3. **Recovery delay** — The cooldown period means you continue using the fallback even after the provider recovers. Shorter cooldowns risk re-tripping on transient issues.
4. **Complexity** — Adds state management to your inference path. In distributed systems, circuit state must be shared across instances or each instance manages its own state.

## Failure Modes

### Flash Trip on Latency Spikes
**Trigger**: A momentary latency spike (provider garbage collection, network jitter) causes enough requests to breach the timeout threshold.
**Symptom**: Circuit opens unnecessarily, routing all traffic to the fallback model. Users experience a quality downgrade for the entire cooldown period even though the primary recovered in seconds.
**Mitigation**: Use a two-signal approach: require both error rate AND latency percentile to breach thresholds before opening. Add a "half-open" probe phase that tests the primary before committing to fallback.

### Fallback Avalanche
**Trigger**: Primary provider goes down, causing a circuit open. All traffic shifts to the fallback, which is not provisioned for full load.
**Symptom**: Fallback provider also degrades or rate-limits under the sudden traffic surge. Both paths are now unhealthy.
**Mitigation**: Load-test the fallback at full production volume. Implement request shedding with graceful degradation (queue, retry with backoff, or partial service) rather than hard-shifting 100% of traffic instantly.

### Split-Brain Circuit State
**Trigger**: Multiple gateway instances each maintain their own circuit state without synchronization.
**Symptom**: Some instances route to the primary (circuit closed) while others route to the fallback (circuit open). Inconsistent user experience and difficulty debugging.
**Mitigation**: Use shared state (Redis, distributed cache) for circuit status, or accept per-instance circuits but ensure each has sufficient traffic for statistically valid failure detection.

## Implementation Example

```python
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


@dataclass
class CircuitBreaker:
    failure_threshold: float = 0.5
    window_size: int = 20
    cooldown_seconds: float = 30.0
    half_open_max_probes: int = 3

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _results: deque = field(default_factory=deque, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _half_open_successes: int = field(default=0, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._opened_at >= self.cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_successes = 0
            return self._state

    def should_allow_request(self) -> bool:
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return True
        return False

    def record_success(self) -> None:
        with self._lock:
            self._results.append(True)
            if len(self._results) > self.window_size:
                self._results.popleft()

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.half_open_max_probes:
                    self._state = CircuitState.CLOSED
                    self._results.clear()

    def record_failure(self) -> None:
        with self._lock:
            self._results.append(False)
            if len(self._results) > self.window_size:
                self._results.popleft()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                return

            if len(self._results) >= self.window_size:
                failure_rate = 1 - (sum(self._results) / len(self._results))
                if failure_rate >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._opened_at = time.monotonic()

    def record_latency_violation(self) -> None:
        self.record_failure()


async def resilient_completion(
    breaker: CircuitBreaker,
    primary_fn,
    fallback_fn,
    messages: list[dict],
    latency_budget_ms: float = 5000.0,
) -> dict:
    if breaker.should_allow_request():
        start = time.monotonic()
        try:
            result = await primary_fn(messages=messages)
            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms > latency_budget_ms:
                breaker.record_latency_violation()
            else:
                breaker.record_success()
            return result
        except Exception:
            breaker.record_failure()

    return await fallback_fn(messages=messages)
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| LiteLLM | Open-source proxy | Built-in circuit breaker with configurable thresholds per provider |
| Portkey | Managed gateway | Automatic failover with circuit breaker semantics |
| Resilience4j | Java library | Generic circuit breaker, adaptable for LLM calls |
| Polly (.NET) | .NET library | Circuit breaker policies for .NET applications |
| Custom implementation | DIY | Necessary when latency and quality (not just errors) define failures |

## Related Patterns

- **[Fallback Chain](/AI-Engineering-Patterns/patterns/inference-and-serving/fallback-chain/)** — The circuit breaker decides when to activate the fallback chain.
- **[Graceful Degradation Pattern](/AI-Engineering-Patterns/patterns/reliability/graceful-degradation/)** — Fallback behavior when the circuit is open.
- **[Health Check Pattern](/AI-Engineering-Patterns/patterns/reliability/health-check/)** — Health checks complement circuit breakers with proactive detection.
- **[LLM Gateway Pattern](/AI-Engineering-Patterns/patterns/inference-and-serving/llm-gateway/)** — The gateway is the natural place to implement circuit breaker logic.
- **[SLO Pattern for AI](/AI-Engineering-Patterns/patterns/observability/slo-for-ai/)** — SLOs define the thresholds that trigger circuit breaker trips.

## Further Reading

- [Circuit Breaker — Martin Fowler](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Release It! Design and Deploy Production-Ready Software — Michael Nygard](https://pragprog.com/titles/mnee2/release-it-second-edition/)
- [LLM Reliability Patterns — Anthropic Cookbook](https://github.com/anthropics/anthropic-cookbook)
