---
title: LLM Gateway
pillar: inference-and-serving
status: validated-in-production
tags: [gateway, routing, observability, cost, multi-provider]
related:
  - Model Router Pattern
  - Fallback Chain
  - Semantic Caching
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Centralized proxy for API key management, rate limiting, logging, and multi-provider routing.
sidebar:
  order: 1
---

## What It Is

An LLM Gateway is a centralized proxy layer that sits between your application code and LLM provider APIs. All inference requests flow through the gateway, which handles authentication, routing, rate limiting, logging, cost tracking, and failover. It is the single control plane for every model interaction in your system.

## The Problem It Solves

Without a gateway, every service that calls an LLM embeds its own API keys, retry logic, error handling, and logging. This creates several failure modes:

- API keys scattered across services, impossible to rotate quickly.
- No centralized view of spend, latency, or error rates across providers.
- Each service implements its own retry and fallback logic (or none at all).
- No way to enforce rate limits or spend caps across the organization.
- Provider switches require code changes in every calling service.

## How It Works

<pre class="mermaid">
flowchart LR
    subgraph S["Application Services"]
      A["Service A"]
      B["Service B"]
      C["Service C"]
    end

    subgraph G["LLM Gateway"]
      D["Auth + policy checks"]
      E["Routing + retries + failover"]
      F["Response normalization"]
    end

    subgraph P["Providers"]
      P1["OpenAI API"]
      P2["Anthropic API"]
      P3["Self-hosted model API"]
    end

    A --> D
    B --> D
    C --> D
    D --> E --> F
    F --> P1
    F --> P2
    F --> P3
    F --> M["Logs, metrics, and cost budgets"]
</pre>

1. Application services send inference requests to the gateway using a unified API format.
2. The gateway resolves which provider and model to use based on routing rules.
3. The gateway injects the correct API key and transforms the request to the provider's format.
4. The response is logged, metered, and returned to the calling service in a normalized format.
5. On failure, the gateway applies retry logic and fallback rules before returning an error.

## When to Use It

- You call LLMs from more than one service or team.
- You use (or plan to use) more than one LLM provider.
- You need centralized cost tracking and spend limits.
- You need consistent logging and tracing across all model calls.
- You want to swap providers or models without changing application code.

## When not to Use It

- You have a single service making occasional LLM calls with one provider. The overhead of running a gateway is not justified until you have multiple callers or need to switch providers.
- Your application is a prototype or proof-of-concept. Direct API calls are fine for validation. Add the gateway when you move to production.
- Latency is so critical that even the small overhead of an extra network hop (~1-5ms) is unacceptable. This is rare but relevant for ultra-low-latency serving paths.

## Trade-offs

1. **Added latency** — Every request adds a network hop. Typically 1-5ms, but can matter at the margins for streaming-first applications.
2. **Single point of failure** — The gateway must be highly available. A gateway outage takes down all LLM calls. Requires redundancy planning.
3. **Operational complexity** — Another service to deploy, monitor, and maintain. Not free for small teams.
4. **Feature lag** — New provider features (streaming modes, tool calling changes) require gateway updates before applications can use them.

## Failure Modes

### Gateway Becomes the Bottleneck
**Trigger**: Gateway is deployed as a single instance or with insufficient scaling, and traffic exceeds its capacity.
**Symptom**: All LLM calls across all services experience increased latency or timeouts simultaneously, even though the underlying providers are healthy.
**Mitigation**: Deploy the gateway with horizontal auto-scaling. Add health checks that include throughput metrics, not just liveness. Load-test the gateway independently from providers.

### Silent Credential Rotation Failure
**Trigger**: API key rotation on one provider succeeds but the gateway reads cached credentials.
**Symptom**: Requests to a single provider start failing with 401/403 errors. Other providers work fine. Teams blame the provider before checking the gateway.
**Mitigation**: Gateway should validate credentials on rotation and emit a specific alert on authentication failures distinct from rate-limit or model errors.

### Logging Amplifies Costs
**Trigger**: Verbose logging is enabled (full prompts and completions) without sampling or size limits.
**Symptom**: Log storage costs approach or exceed LLM inference costs. Log ingestion pipelines lag, causing alert delays.
**Mitigation**: Log prompt/completion hashes by default; store full payloads only for sampled requests or flagged interactions. Set retention policies.

## Implementation Example

```python
import hashlib
import hmac
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    models: list[str]
    timeout: float = 30.0
    max_retries: int = 2


@dataclass
class GatewayMetrics:
    requests: int = 0
    failures: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0


class LLMGateway:
    def __init__(self, providers: list[ProviderConfig]):
        self._providers = {p.name: p for p in providers}
        self._model_to_provider: dict[str, str] = {}
        self._metrics: dict[str, GatewayMetrics] = {}
        for p in providers:
            self._metrics[p.name] = GatewayMetrics()
            for model in p.models:
                self._model_to_provider[model] = p.name

    def _resolve_provider(self, model: str) -> ProviderConfig:
        provider_name = self._model_to_provider.get(model)
        if not provider_name:
            raise ValueError(f"No provider configured for model: {model}")
        return self._providers[provider_name]

    async def chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> dict:
        provider = self._resolve_provider(model)
        metrics = self._metrics[provider.name]
        metrics.requests += 1

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=provider.timeout) as client:
            for attempt in range(provider.max_retries + 1):
                try:
                    response = await client.post(
                        f"{provider.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {provider.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    elapsed = (time.monotonic() - start) * 1000
                    metrics.total_latency_ms += elapsed
                    usage = result.get("usage", {})
                    metrics.total_tokens += usage.get("total_tokens", 0)
                    return result
                except httpx.HTTPStatusError:
                    if attempt == provider.max_retries:
                        metrics.failures += 1
                        raise

        raise RuntimeError("Unreachable")

    def get_metrics(self) -> dict[str, GatewayMetrics]:
        return dict(self._metrics)
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| LiteLLM | Open-source proxy | Supports 100+ providers, OpenAI-compatible API |
| Portkey | Managed gateway | Built-in caching, fallback, and observability |
| Helicone | Logging-focused proxy | Strong on analytics and cost tracking |
| Kong AI Gateway | Enterprise gateway | Extends existing Kong infrastructure for LLM routing |
| Custom (nginx/Envoy) | DIY | Maximum control, highest operational burden |

## Related Patterns

- **[Model Router Pattern](/AI-Engineering-Patterns/patterns/inference-and-serving/model-router/)** — Routes to different models by complexity. Often implemented inside the gateway.
- **[Fallback Chain](/AI-Engineering-Patterns/patterns/inference-and-serving/fallback-chain/)** — Provider failover logic. The gateway is the natural place to implement it.
- **[Semantic Caching](/AI-Engineering-Patterns/patterns/inference-and-serving/semantic-caching/)** — Cache layer that integrates at the gateway level.
- **[Cost Attribution Pattern](/AI-Engineering-Patterns/patterns/observability/cost-attribution/)** — The gateway is the source of truth for cost data.
- **[Span-Level Tracing Pattern](/AI-Engineering-Patterns/patterns/observability/span-level-tracing/)** — The gateway generates the root span for model interactions.

## Further Reading

- [LiteLLM Proxy Documentation](https://docs.litellm.ai/docs/simple_proxy)
- [Building an LLM Gateway — Cloudflare AI Gateway Architecture](https://developers.cloudflare.com/ai-gateway/)
- [The LLM Gateway Pattern — Martin Fowler's blog](https://martinfowler.com/articles/exploring-gen-ai.html)
