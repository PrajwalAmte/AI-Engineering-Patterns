---
title: LLM Gateway
pillar: inference-and-serving
status: validated-in-production
tags: [gateway, routing, observability, cost, multi-provider]
related:
  - Model Router
  - Circuit Breaker for LLMs
  - Semantic Caching
  - Span-Level Tracing
  - Token Budget
example: examples/inference_and_serving/llm_gateway.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Put one service between your code and every model provider, and make keys, budgets, routing, retries and logging its job instead of every team's.
sidebar:
  order: 1
---

## What It Is

A gateway is a proxy that every model call goes through. Application code asks for a model alias like `chat-default` using its own internal key. The gateway works out which provider and model serve that alias, attaches the real provider credentials, enforces the team's rate limit and budget, retries or fails over, and records what happened.

It's the API gateway idea applied to LLMs. It matters more for LLMs than for most APIs because each request has a real, variable cost and providers change often.

## The Problem It Solves

The second team that ships an LLM feature usually copies the first team's client code. By the fifth team you have:

- Provider keys in five sets of environment variables, so rotating them means five deploys.
- No single answer to "what did we spend on OpenAI last week, and on what?"
- Five different retry policies, at least one of which retries a 429 instantly in a tight loop.
- No way to cap a runaway batch job before the invoice arrives.
- A provider migration that becomes a quarter-long project because model names are hard-coded everywhere.

## How It Works

<pre class="mermaid">
flowchart LR
    subgraph S["Your services"]
      A["Search"]
      B["Support bot"]
      C["Batch jobs"]
    end
    subgraph G["Gateway"]
      D["Auth: internal key → team"]
      E["Rate limit + budget check"]
      F["Alias → deployments, retry, fail over"]
      L["Log: team, model, tokens, cost, latency"]
    end
    A & B & C --> D --> E --> F
    F --> P1["Provider A"]
    F --> P2["Provider B"]
    F --> P3["Self-hosted"]
    F --> L
</pre>

1. A service sends a request with its internal key and a model alias.
2. The gateway maps the key to a team and checks that team's rate limit and remaining budget.
3. It resolves the alias to an ordered list of deployments and calls the first one. If that call fails, it tries the next.
4. It counts tokens, works out the cost, charges it to the team, and writes a log record. The record stores a hash of the prompt, not the prompt itself.
5. The service gets back a normalized response and never learns which provider answered.

## When to Use It

- More than one service or team calls models.
- You use, or expect to use, more than one provider or model family.
- Someone has asked "how much does feature X cost us?" and nobody could answer.
- You want to change models through config, without redeploying callers.

## When NOT to Use It

- **One service, one provider, early days.** Call the SDK directly. Add a gateway when the second caller appears, not before.
- **You'd be building it yourself for no reason.** LiteLLM, Portkey, Kong, Cloudflare and the cloud vendors all ship one. Building your own is only worth it when you need policy hooks those products don't offer.
- **A hard latency floor.** The extra hop usually costs a few milliseconds. That's irrelevant next to model latency, but it can matter for on-device or ultra-low-latency paths.

## Trade-offs

- **It's now on the critical path for everything.** A gateway outage takes down every AI feature at once. Run several replicas, and decide in advance whether callers may bypass it in an emergency (most teams say no, to keep keys contained).
- **Feature lag.** When a provider ships a new parameter or streaming mode, nobody can use it until the gateway supports it. Allow a raw pass-through for provider-specific fields.
- **Logs cost money.** Logging full prompts and completions can cost as much as inference and creates a pile of sensitive data. Hash by default and sample full payloads.

## Failure Modes

**The gateway becomes the bottleneck.** It was load-tested at launch traffic, and a year later every AI feature slows down at once while the providers are healthy. Autoscale on in-flight requests, not CPU. Streaming responses hold connections open for a long time while using very little CPU.

**Credential rotation fails quietly.** A key is rotated at the provider but the gateway keeps a cached copy. Calls to that one provider start returning 401. If 401s are lumped in with "provider errors", failover hides the problem until the backup's rate limit runs out too. Alert on auth errors separately.

**Budget checks race.** The budget check runs before the call and the charge is recorded after it. Fifty concurrent requests can all pass the check and overshoot the cap. That's acceptable for monthly budgets. For hard caps, reserve the estimated cost up front and settle the difference afterwards.

## Implementation Example

This is the core of a gateway: virtual keys, per-team rate limits and budgets, alias-based fallback, and cost attribution. It's meant for reading. In production you'd run an existing gateway and use this to understand what it should be doing.

```bash
cd examples && pytest inference_and_serving/test_llm_gateway.py
```

<!-- example: examples/inference_and_serving/llm_gateway.py -->
```python
"""LLM Gateway.

One place where every model call is authenticated, budgeted, routed, retried
and logged. Callers ask for a model *alias* ("chat-default"); the gateway
decides which provider deployment serves it.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field

Provider = Callable[[str], str]


class GatewayError(Exception):
    pass


class Unauthorized(GatewayError):
    pass


class RateLimited(GatewayError):
    pass


class BudgetExceeded(GatewayError):
    pass


@dataclass
class Deployment:
    name: str
    call: Provider
    usd_per_1k_tokens: float


@dataclass
class Team:
    name: str
    monthly_budget_usd: float
    requests_per_minute: int
    spent_usd: float = 0.0
    _window_start: float = 0.0
    _window_count: int = 0


@dataclass
class LogRecord:
    team: str
    alias: str
    deployment: str | None
    prompt_sha256: str  # hash, not the prompt: full payloads belong in sampled storage
    tokens: int
    cost_usd: float
    latency_s: float
    error: str | None = None


@dataclass
class Gateway:
    routes: dict[str, list[Deployment]]  # alias -> deployments in fallback order
    keys: dict[str, Team]  # virtual API key -> team
    clock: Callable[[], float] = time.monotonic
    count_tokens: Callable[[str], int] = lambda text: max(1, len(text) // 4)
    log: list[LogRecord] = field(default_factory=list)

    def complete(self, api_key: str, alias: str, prompt: str) -> str:
        team = self.keys.get(api_key)
        if team is None:
            raise Unauthorized("unknown API key")
        self._check_rate_limit(team)
        if team.spent_usd >= team.monthly_budget_usd:
            raise BudgetExceeded(f"{team.name} has spent its ${team.monthly_budget_usd:.2f} budget")
        if alias not in self.routes:
            raise GatewayError(f"unknown model alias {alias!r}")

        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
        last_error = None
        for deployment in self.routes[alias]:
            start = self.clock()
            try:
                text = deployment.call(prompt)
            except Exception as exc:  # provider-specific errors stay behind the gateway
                last_error = f"{deployment.name}: {exc}"
                self.log.append(LogRecord(team.name, alias, deployment.name, prompt_hash, 0, 0.0,
                                          self.clock() - start, error=str(exc)))
                continue

            tokens = self.count_tokens(prompt) + self.count_tokens(text)
            cost = tokens / 1000 * deployment.usd_per_1k_tokens
            team.spent_usd += cost
            self.log.append(LogRecord(team.name, alias, deployment.name, prompt_hash, tokens, cost,
                                      self.clock() - start))
            return text

        raise GatewayError(f"all deployments for {alias!r} failed; last error: {last_error}")

    def _check_rate_limit(self, team: Team) -> None:
        now = self.clock()
        if now - team._window_start >= 60:
            team._window_start, team._window_count = now, 0
        if team._window_count >= team.requests_per_minute:
            raise RateLimited(f"{team.name} exceeded {team.requests_per_minute} requests/minute")
        team._window_count += 1

    def spend_by_team(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for record in self.log:
            totals[record.team] = totals.get(record.team, 0.0) + record.cost_usd
        return totals
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| LiteLLM Proxy | Open source, OpenAI-compatible API over 100+ providers, virtual keys and budgets |
| Portkey | Managed or self-hosted; fallbacks, caching, guardrail hooks |
| Kong AI Gateway | Adds LLM plugins to an existing Kong deployment |
| Cloudflare AI Gateway | Edge-hosted; caching, rate limiting, analytics |
| Envoy AI Gateway | Kubernetes-native, built on Envoy Gateway |

## Related Patterns

- [Model Router](model-router.md) decides which model a request deserves. It usually runs inside the gateway.
- [Circuit Breaker for LLMs](../reliability/circuit-breaker.md) is how the gateway knows to stop sending traffic to a degraded deployment.
- [Semantic Caching](semantic-caching.md) is checked before routing. A cache hit costs nothing.
- [Span-Level Tracing](../observability-and-evaluation/span-level-tracing.md): the gateway emits the model-call span.
- [Token Budget](../cost-and-efficiency/token-budget.md) limits one request. The gateway's budgets limit a whole team.

## Further Reading

- [LiteLLM Proxy documentation](https://docs.litellm.ai/docs/simple_proxy)
- [Cloudflare AI Gateway documentation](https://developers.cloudflare.com/ai-gateway/)
- [Emerging Patterns in Building GenAI Products](https://martinfowler.com/articles/gen-ai-patterns/), Bharani Subramaniam and Martin Fowler
