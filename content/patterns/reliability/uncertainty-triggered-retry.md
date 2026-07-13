---
title: Uncertainty-Triggered Retry
pillar: reliability
status: emerging
tags: [reliability, retry, confidence, quality-assurance, hedge-detection]
related:
  - Circuit Breaker for LLMs
  - Model Router
  - LLM-as-Judge
contributors: ["@PrajwalAmte"]
last_updated: "2026-07"
description: Detect low-confidence LLM responses and retry with stronger models or improved prompts before serving degraded answers.
sidebar:
  order: 2
---

## What It Is

Uncertainty-Triggered Retry analyzes LLM responses for confidence signals before serving them to users. When a response exhibits uncertainty markers—low logprob scores, hedge phrases, incomplete structured outputs, or refusal-adjacent language—the system automatically retries the request with a stronger model, chain-of-thought prompting, or a rephrased prompt. Only confident responses are served; uncertain responses trigger remediation.

## The Problem It Solves

LLM providers return HTTP 200 for low-confidence responses that should be treated as soft failures. Unlike hard errors (timeouts, rate limits), these degraded responses appear successful:

- Hedge language: "I'm not entirely sure," "This might be correct," "Possibly..."
- Low logprob scores indicating model uncertainty (when available)
- Incomplete structured outputs with missing required fields
- Refusal-adjacent responses: "I cannot confidently say whether..."

Your system serves these degraded answers to users because the API succeeded. Users experience poor quality without triggering error handlers or alerts. Unlike circuit breakers that detect provider-level failures, this pattern detects response-level quality degradation.

## How It Works

<pre class="mermaid">
flowchart TD
    A[Send request to base model] --> B[Receive response]
    B --> C{Analyze confidence signals}
    C -->|High confidence| D[Return response]
    C -->|Low confidence detected| E[Retry strategy]
    E --> F[Upgrade to stronger model]
    E --> G[Add chain-of-thought]
    E --> H[Rephrase prompt]
    F --> I[Send retry request]
    G --> I
    H --> I
    I --> J[Receive retry response]
    J --> K{Confidence improved?}
    K -->|Yes| D
    K -->|No| L[Surface uncertainty to user or escalate]
</pre>

1. **Initial request**: Send query to base model (e.g., GPT-4o-mini, Claude Sonnet)
2. **Confidence analysis**: Examine response for uncertainty signals:
   - Parse logprobs if available (scores below -1.5 indicate uncertainty)
   - Detect hedge phrases with regex patterns
   - Validate structured outputs for completeness
   - Check for refusal-adjacent language
3. **Threshold check**: Calculate aggregate uncertainty score (0.0-1.0)
4. **Retry decision**: If score exceeds threshold (e.g., 0.4), trigger retry:
   - **Model upgrade**: Switch to stronger model (GPT-4, Claude Opus)
   - **Prompt engineering**: Add "Think step-by-step before answering"
   - **Rephrasing**: Make query more specific or constrained
5. **Cap retries**: Limit to 1 retry to prevent cost explosion
6. **Final disposition**: Return retry result if improved, otherwise surface uncertainty explicitly

## When to Use It

- User-facing applications where low-quality answers damage trust
- Structured output tasks where completeness is critical (JSON, form filling)
- High-stakes domains (legal, medical, financial) requiring confident answers
- You have budget headroom for occasional retry costs (10-20% of requests)
- The base model is fast but occasionally low-confidence (smaller models, fine-tuned models)
- Logprobs or confidence signals are available from your provider

## When NOT to Use It

- Creative or subjective tasks where uncertainty is acceptable (brainstorming, poetry)
- High-throughput batch processing where latency and cost are paramount
- You're already using the strongest available model (no retry target)
- Budget is tightly constrained and cannot absorb 20-40% cost increase on uncertain queries
- Request volume is too low to justify the complexity (< 100 requests/day)
- Tasks where hedge language is part of legitimate answers ("The evidence suggests this may indicate...")

## Trade-offs

1. **Cost amplification** — If 20% of requests are uncertain, 20% of your inference budget doubles. With expensive models, this can be significant. A $0.10 base request becomes $0.40 if retried with GPT-4.

2. **Latency penalty** — Retry adds 1-3 seconds to uncertain requests. P99 latency increases proportionally to uncertainty rate. Users experience slower responses on edge cases.

3. **Detection accuracy** — Hedge phrase detection has false positives. Responses containing cautious but correct phrasing ("This approach generally works well but may fail if...") trigger unnecessary retries.

4. **Confidence gaming** — If the retry model learns your detection patterns, it may avoid hedge phrases even when genuinely uncertain, masking poor quality behind confident-sounding but wrong answers.

## Failure Modes

### Retry Loop on Intractable Queries
**Trigger**: Query is genuinely unanswerable with available context. Base model hedges, stronger model also hedges, triggering another retry.  
**Symptom**: Cost explosion as system retries multiple times. Latency balloons to 5-10 seconds. User still receives uncertain answer.  
**Mitigation**: Hard cap at 1 retry. If retry also fails confidence threshold, return explicit "insufficient information" response rather than uncertain answer. Track queries that fail twice for manual review.

### False Positive on Cautious Reasoning
**Trigger**: Model provides correct answer with appropriate epistemic humility ("Based on the evidence, this likely indicates X, though other interpretations are possible").  
**Symptom**: Unnecessary retry wastes cost. Retry response may actually be worse (overconfident, less nuanced).  
**Mitigation**: Use logprobs as primary signal when available; hedge phrases as secondary. Whitelist acceptable caution phrases in high-stakes domains. Manually review flagged responses to tune detection.

### Uncertainty Signal Unavailability
**Trigger**: Provider does not expose logprobs (e.g., Azure OpenAI, some Claude configurations). Only hedge phrase detection available.  
**Symptom**: Detection relies solely on text analysis, which is less reliable. False negative rate increases.  
**Mitigation**: Negotiate API access with logprobs if possible. Alternatively, train a lightweight confidence classifier on labeled data (confident vs. uncertain responses). Use embedding-based similarity to known-uncertain patterns.

## Implementation Example

```python
import re
from typing import Optional, Callable
from dataclasses import dataclass

@dataclass
class LLMResponse:
    text: str
    logprobs: Optional[list[float]] = None
    metadata: dict = None

# Hedge phrase patterns compiled for efficiency
HEDGE_PATTERNS = [
    re.compile(r"\b(might|maybe|possibly|perhaps|could be)\b", re.IGNORECASE),
    re.compile(r"\b(I think|not sure|unclear|uncertain|difficult to say)\b", re.IGNORECASE),
    re.compile(r"\b(I'm not certain|cannot confidently|may or may not)\b", re.IGNORECASE),
]

def calculate_uncertainty(response: LLMResponse) -> float:
    """
    Return uncertainty score 0.0 (certain) to 1.0 (very uncertain).
    Combines logprobs and hedge phrase detection.
    """
    score = 0.0
    
    # Check hedge language (weight: 0.3 per match, cap at 0.6)
    hedge_matches = sum(1 for pattern in HEDGE_PATTERNS if pattern.search(response.text))
    score += min(hedge_matches * 0.3, 0.6)
    
    # Check logprobs if available (weight: up to 0.5)
    if response.logprobs and len(response.logprobs) > 0:
        avg_logprob = sum(response.logprobs) / len(response.logprobs)
        # Logprobs below -1.5 indicate uncertainty; map to 0-0.5 score
        if avg_logprob < -1.5:
            score += min((abs(avg_logprob) - 1.5) * 0.2, 0.5)
    
    return min(score, 1.0)


async def llm_call(
    model: str,
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.7,
    logprobs: bool = False
) -> LLMResponse:
    """Placeholder for actual LLM API call"""
    # Implementation depends on your provider (OpenAI, Anthropic, etc.)
    pass


async def retry_on_uncertainty(
    prompt: str,
    base_model: str = "gpt-4o-mini",
    stronger_model: str = "gpt-4",
    system_prompt: Optional[str] = None,
    uncertainty_threshold: float = 0.4,
    temperature: float = 0.7,
) -> LLMResponse:
    """
    Send request to base model. If response is uncertain, retry with stronger model.
    Returns the best available response.
    """
    
    # First attempt with base model
    response = await llm_call(
        model=base_model,
        prompt=prompt,
        system=system_prompt,
        temperature=temperature,
        logprobs=True  # Request logprobs if available
    )
    
    uncertainty = calculate_uncertainty(response)
    
    # If confident enough, return immediately
    if uncertainty < uncertainty_threshold:
        response.metadata = {"uncertainty": uncertainty, "retried": False}
        return response
    
    # Retry with stronger model and chain-of-thought
    cot_prompt = f"{prompt}\n\nThink step-by-step and explain your reasoning before providing a final answer."
    
    retry_response = await llm_call(
        model=stronger_model,
        prompt=cot_prompt,
        system=system_prompt,
        temperature=temperature * 0.8,  # Slightly lower temperature for retry
        logprobs=True
    )
    
    retry_uncertainty = calculate_uncertainty(retry_response)
    retry_response.metadata = {
        "uncertainty": retry_uncertainty,
        "retried": True,
        "original_uncertainty": uncertainty
    }
    
    return retry_response


# Usage example
async def main():
    response = await retry_on_uncertainty(
        prompt="What is the capital of France?",
        system_prompt="You are a helpful assistant. Be direct and confident when you know the answer.",
        uncertainty_threshold=0.4
    )
    
    if response.metadata.get("uncertainty", 0) > 0.6:
        print(f"Warning: High uncertainty ({response.metadata['uncertainty']:.2f})")
        print("Consider human review or returning 'insufficient information' response")
    
    print(response.text)
```

## Tool Landscape

| Tool | Type | Notes |
|------|------|-------|
| OpenAI API | Provider | Supports logprobs parameter for confidence signals; use `logprobs=true` |
| Anthropic Claude | Provider | Does not expose logprobs; must rely on text-based detection |
| LiteLLM | Open-source proxy | Provides normalized logprobs across providers where available |
| LangChith | Observability | Can log uncertainty scores and retry rates for analysis |
| Guardrails AI | Validation | Supports custom validators for confidence checking |
| Custom classifier | DIY | Fine-tune small model (DistilBERT, small LLama) to detect uncertainty from response text |

## Related Patterns

- **[Circuit Breaker for LLMs](circuit-breaker.md)** — Circuit breaker detects provider-level failures; uncertainty retry detects response-level quality issues. Use both: circuit breaker for hard failures, uncertainty retry for soft degradation.
- **Model Router** — Route uncertain responses to stronger models without full retry; requires router to accept "uncertainty score" as routing signal.
- **LLM-as-Judge** — Use a separate judge model to score response quality instead of rule-based uncertainty detection; more accurate but adds latency and cost.

## Further Reading

- [Teaching Models to Express Their Uncertainty in Words](https://arxiv.org/abs/2205.14334) — Research on eliciting calibrated confidence from LLMs
- [Semantic Uncertainty: Linguistic Invariances for Uncertainty Estimation in Natural Language Generation](https://arxiv.org/abs/2302.09664) — Academic approach to quantifying LLM uncertainty
- [OpenAI Logprobs Documentation](https://platform.openai.com/docs/api-reference/chat/create#chat-create-logprobs) — Technical reference for extracting confidence signals
- [The Alignment Problem — Brian Christian](https://brianchristian.org/the-alignment-problem/) — Chapter on uncertainty and calibration in ML systems
