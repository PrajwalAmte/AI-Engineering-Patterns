---
title: Request Hedging for LLMs
pillar: reliability
status: emerging
tags: [reliability, latency, tail-latency, redundancy, racing]
related:
  - Circuit Breaker for LLMs
  - Model Router
  - LLM Gateway
contributors: ["@PrajwalAmte"]
last_updated: "2026-07"
description: Send duplicate requests to multiple providers and return the fastest adequate response to mitigate tail latency.
sidebar:
  order: 3
---

## What It Is

Request Hedging for LLMs sends identical inference requests to 2-3 providers simultaneously (or after a short delay), accepts the first response that meets quality criteria, and cancels the remaining in-flight requests. This technique, adapted from Google's "Tail at Scale" paper, reduces p99 latency at the cost of occasional duplicate inference charges. Unlike naive racing of all requests, hedging uses a delay threshold to avoid unnecessary duplication.

## The Problem It Solves

LLM inference has high tail latency. P99 response times can be 5-10x slower than P50 due to:

- Backend batching and queueing on provider infrastructure
- Cold starts when scaling up capacity
- Spot instance interruptions or transient network issues
- Load imbalance across provider regions

Traditional timeout strategies discard the work already performed by the slow request. Retrying after timeout doubles latency. Waiting for the slowest request degrades user experience in interactive applications where every second matters.

Request hedging preserves the work from both requests: whichever completes first wins, and the loser is canceled. P99 latency approaches P50 of the faster provider, not P99 of the slower.

## How It Works

<pre class="mermaid">
sequenceDiagram
    participant Client
    participant Primary as Primary Provider
    participant Backup as Backup Provider
    
    Client->>Primary: Request (t=0ms)
    
    Note over Client: Wait for hedge delay<br/>(e.g., p95 latency threshold)
    
    alt Primary responds within delay
        Primary-->>Client: Response (t=800ms)
        Note over Client: Return primary response<br/>No hedge needed
    else Hedge delay exceeded
        Client->>Backup: Hedged request (t=2000ms)
        
        alt Primary completes first
            Primary-->>Client: Response (t=2500ms)
            Client->>Backup: Cancel request
            Note over Client: Return primary response
        else Backup completes first
            Backup-->>Client: Response (t=2300ms)
            Client->>Primary: Cancel request
            Note over Client: Return backup response
        end
    end
</pre>

1. **Primary request**: Send to preferred provider with best price/quality ratio
2. **Delay threshold**: Wait for delay period (e.g., provider's p95 latency, typically 2-3 seconds)
3. **Hedge trigger**: If primary hasn't responded by delay threshold, send identical request to backup provider
4. **Race**: Wait for first adequate response from either provider
5. **Quality check** (optional): Validate response meets minimum quality bar before accepting
6. **Cancel losers**: Immediately cancel the slower in-flight request to avoid paying for unused work
7. **Metric collection**: Track hedge rate, latency distribution, and cost overhead

The delay threshold is critical: too short and most requests hedge unnecessarily (2x cost); too long and hedging doesn't help tail latency.

## When to Use It

- User-facing interactive applications with strict latency SLOs (e.g., chatbots, real-time assistants)
- P99 latency is a key product metric and current tail is unacceptable
- You have 2+ providers with similar quality and pricing
- Cost of occasional duplicate requests < cost of SLO violations or user churn
- Providers support request cancellation or charge only for completed tokens
- Your application is read-only (no side effects like writes, tool calls that modify state)

## When NOT to Use It

- Batch processing or background tasks where latency is irrelevant
- Only one provider available (no backup to hedge to)
- Providers charge per-request submission regardless of cancellation
- Requests have side effects (database writes, API calls to external services)
- Your latency budget is loose (p99 < 10s is acceptable)
- Cost optimization is the primary goal (hedging increases spend)
- Request rate is low enough that tail latency is statistically insignificant

## Trade-offs

1. **Cost overhead** — 10-20% of requests exceed the hedge delay, triggering duplicate inference. If hedge rate is 15% and you pay for both requests, total cost increases by 15%. Some providers charge per-token-generated, so canceling early saves most of the cost.

2. **Provider fairness** — Backup provider receives mostly slow/problematic requests (those that exceeded the delay). This skewed traffic pattern may trigger rate limits or appear as abusive behavior. Rotate which provider is "primary" to balance load.

3. **Cancellation reliability** — Not all LLM providers support mid-stream request cancellation. If cancellation fails, you pay full price for both requests. OpenAI and Anthropic support cancellation via connection close; some proxy layers do not propagate cancellation.

4. **Quality variance risk** — First response may be fast but lower quality (hallucination, incomplete reasoning). Slower response may be better but gets canceled. Mitigation: add quality gate that rejects inadequate fast responses.

## Failure Modes

### Hedge Thrashing
**Trigger**: Delay threshold set too low (e.g., below p50 latency). Most requests exceed the delay and trigger hedging.  
**Symptom**: Hedge rate climbs to 60-80%, nearly doubling inference costs with minimal latency improvement. Backup provider may rate-limit due to excessive traffic.  
**Mitigation**: Calibrate delay threshold to provider's p90-p95 latency from historical data. Monitor hedge rate; target 10-20%. Use exponential moving average to adapt threshold dynamically as provider latency shifts.

### Quality Divergence
**Trigger**: Primary and backup providers use different models or configurations. Backup responds faster but with lower quality (hallucination, incomplete answer).  
**Symptom**: Fast but wrong responses served to users. Quality metrics degrade while latency improves.  
**Mitigation**: Add quality gate: validate response for structural correctness (JSON parsing, required fields), minimum length, or absence of refusal language before accepting. If fast response fails quality check, wait for slower response.

### Cancellation Failure and Cost Explosion
**Trigger**: Provider or proxy layer does not honor cancellation. Both requests run to completion and are billed.  
**Symptom**: Cost doubles on all hedged requests (15-20% of traffic), increasing monthly spend by 15-20%. Difficult to detect without detailed per-request cost tracking.  
**Mitigation**: Test cancellation behavior in staging before production rollout. Monitor per-request costs and flag anomalies. If cancellation is unreliable, reduce hedge rate by increasing delay threshold or disable hedging for that provider.

### Quota Exhaustion on Backup
**Trigger**: Primary provider degrades for extended period. Most requests hedge, flooding backup provider.  
**Symptom**: Backup provider hits rate limits or quota caps. Both paths fail, leaving no working fallback.  
**Mitigation**: Reserve backup provider quota for hedged traffic (e.g., 20% of primary capacity). Combine with circuit breaker pattern: if primary fails consistently, open circuit and route all traffic to backup without hedging.

## Implementation Example

```python
import asyncio
import time
from typing import Callable, Optional, Any
from dataclasses import dataclass

@dataclass
class HedgedResponse:
    content: str
    provider: str
    latency_ms: float
    hedged: bool

class LLMProvider:
    """Minimal provider interface for hedging"""
    
    def __init__(self, name: str, api_call: Callable):
        self.name = name
        self.api_call = api_call
    
    async def complete(self, prompt: str, **kwargs) -> str:
        """Call provider API and return response text"""
        return await self.api_call(prompt, **kwargs)


async def hedged_completion(
    prompt: str,
    primary: LLMProvider,
    backup: LLMProvider,
    hedge_delay_ms: int = 2000,
    quality_check: Optional[Callable[[str], bool]] = None,
    **model_kwargs
) -> HedgedResponse:
    """
    Send request to primary provider. If no response within hedge_delay_ms,
    send to backup. Return first adequate response and cancel the other.
    
    Args:
        prompt: Input prompt for the LLM
        primary: Primary provider (best price/quality)
        backup: Backup provider for hedging
        hedge_delay_ms: Delay before sending hedge request (default: 2000ms)
        quality_check: Optional function to validate response quality
        **model_kwargs: Additional parameters passed to provider APIs
    
    Returns:
        HedgedResponse with content, provider name, latency, and hedge flag
    """
    
    start_time = time.monotonic()
    hedged = False
    
    # Start primary request
    primary_task = asyncio.create_task(
        primary.complete(prompt, **model_kwargs)
    )
    backup_task = None
    
    try:
        # Wait up to hedge_delay for primary response
        response = await asyncio.wait_for(
            primary_task,
            timeout=hedge_delay_ms / 1000.0
        )
        
        # Check quality if validator provided
        if quality_check is None or quality_check(response):
            latency_ms = (time.monotonic() - start_time) * 1000
            return HedgedResponse(
                content=response,
                provider=primary.name,
                latency_ms=latency_ms,
                hedged=False
            )
        
        # Primary response failed quality check; will hedge below
        
    except asyncio.TimeoutError:
        # Hedge delay exceeded without response; launch backup
        hedged = True
        backup_task = asyncio.create_task(
            backup.complete(prompt, **model_kwargs)
        )
    
    # Race remaining tasks
    pending_tasks = {primary_task}
    if backup_task:
        pending_tasks.add(backup_task)
    
    done, pending = await asyncio.wait(
        pending_tasks,
        return_when=asyncio.FIRST_COMPLETED
    )
    
    # Cancel slower request(s)
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    # Extract result from winner
    winner_task = done.pop()
    response = winner_task.result()
    
    # Determine which provider won
    provider_name = backup.name if winner_task == backup_task else primary.name
    latency_ms = (time.monotonic() - start_time) * 1000
    
    return HedgedResponse(
        content=response,
        provider=provider_name,
        latency_ms=latency_ms,
        hedged=hedged
    )


# Example quality check function
def validate_json_response(response: str) -> bool:
    """Example: check if response is valid JSON with required fields"""
    try:
        import json
        data = json.loads(response)
        return "answer" in data  # Require specific field
    except (json.JSONDecodeError, KeyError):
        return False


# Usage example
async def main():
    # Define providers (simplified; real implementation calls actual APIs)
    primary = LLMProvider("openai-gpt4o-mini", api_call=lambda p, **kw: openai_api(p, **kw))
    backup = LLMProvider("anthropic-claude-sonnet", api_call=lambda p, **kw: anthropic_api(p, **kw))
    
    result = await hedged_completion(
        prompt="Explain quantum entanglement in simple terms",
        primary=primary,
        backup=backup,
        hedge_delay_ms=2000,
        temperature=0.7
    )
    
    print(f"Response from {result.provider} (latency: {result.latency_ms:.0f}ms, hedged: {result.hedged})")
    print(result.content)
```

## Tool Landscape

| Tool | Type | Notes |
|------|------|-------|
| LiteLLM | Open-source proxy | Supports fallback routing; does not natively implement hedging with racing |
| Portkey | Managed gateway | Automatic failover with latency-based routing; approximates hedging via fast timeout + fallback |
| Martian | LLM Gateway | Supports request hedging with configurable delay thresholds |
| Custom implementation | DIY | Necessary for fine-grained control over delay thresholds and cancellation logic |
| AWS Step Functions | Orchestration | Can implement hedging logic with parallel states and "first to complete" choice |

## Related Patterns

- **[Circuit Breaker for LLMs](circuit-breaker.md)** — Circuit breaker handles sustained provider failures; hedging handles transient tail latency. Use both: circuit breaker to avoid sending hedges to a failing provider.
- **[Model Router](../inference-and-serving/model-router.md)** — Router selects one provider based on static policy; hedging dynamically selects winner based on actual response time.
- **[LLM Gateway](../inference-and-serving/llm-gateway.md)** — Gateway is the natural implementation point for hedging logic, centralizing latency monitoring and provider orchestration.

## Further Reading

- [The Tail at Scale — Dean & Barroso (Google)](https://research.google/pubs/pub40801/) — Foundational paper introducing hedged requests and tail-tolerant techniques
- [Hedged Requests: Stochastic Response Times — Microsoft Research](https://www.microsoft.com/en-us/research/publication/hedged-requests/) — Analysis of hedging in distributed systems
- [Release It! — Michael Nygard](https://pragprog.com/titles/mnee2/release-it-second-edition/) — Chapter on latency and timeout patterns
- [Designing Data-Intensive Applications — Martin Kleppmann](https://dataintensive.net/) — Section on tail latency amplification in multi-tier systems
