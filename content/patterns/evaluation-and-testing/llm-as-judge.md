---
title: LLM-as-Judge
pillar: evaluation-and-testing
status: validated-in-production
tags: [evaluation, llm-judge, quality, testing, automated-eval]
related:
  - Span-Level Tracing
  - Circuit Breaker for LLMs
  - Model Card Pattern
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Use a strong LLM to evaluate outputs from another model, replacing expensive human evaluation with scalable automated quality scoring.
sidebar:
  order: 1
---

## What It Is

LLM-as-Judge uses a strong language model (the "judge") to evaluate the outputs of another model (the "candidate"). Instead of relying on human evaluators for every quality check, you define evaluation criteria as a structured prompt, feed the candidate's output to the judge model, and receive a score or pass/fail decision. This enables continuous, automated quality measurement at a fraction of the cost and latency of human evaluation.

## The Problem It Solves

AI systems degrade silently. A prompt change, model update, or data shift can reduce output quality without any error being thrown. The standard approaches to catching this have fundamental limitations:

- **Human evaluation** is accurate but does not scale. You cannot have humans review every response in production.
- **Rule-based checks** (regex, keyword matching) catch format issues but miss semantic quality — whether the response is actually helpful, accurate, or safe.
- **Embedding similarity** measures distance from reference outputs but does not capture nuanced quality dimensions like reasoning coherence or factual accuracy.

LLM-as-Judge bridges the gap: it scales like automated checks but evaluates like a human reviewer.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Candidate model output"] --> B["Build judge prompt (query + rubric + output)"]
    C["Reference answer (optional)"] --> B
    B --> D["Judge model evaluates response"]
    D --> E["Structured scores + rationale"]
    E --> F["Aggregate metrics across eval set"]
    F --> G{"Regression detected?"}
    G -->|"Yes"| H["Alert team or block release"]
    G -->|"No"| I["Approve iteration"]
</pre>

1. **Define evaluation criteria** — Create a rubric with specific dimensions: accuracy, helpfulness, safety, formatting, reasoning quality. Each dimension gets a clear scoring guide.
2. **Construct the judge prompt** — Include the original query, the candidate's output, the rubric, and optionally a reference answer. Ask the judge to score each dimension and provide reasoning.
3. **Call the judge model** — Use a stronger or equal-tier model as the judge. The judge returns structured scores with chain-of-thought reasoning for each dimension.
4. **Parse and aggregate** — Extract scores from the judge's response, aggregate across eval sets, and track trends over time.
5. **Alert on regression** — Set thresholds on aggregate scores. When quality drops below threshold, trigger alerts or block deployments.

## When to Use It

- You need continuous quality monitoring in production but cannot afford human review on every response.
- You are running eval suites before deploying prompt or model changes and need a quality gate.
- Your quality dimensions are semantic (helpfulness, accuracy, tone) rather than structural (format, length).
- You have a stronger model available as the judge (e.g., GPT-4o judging GPT-4o-mini outputs).
- You want to scale evaluation across hundreds of test cases that would take human reviewers days.

## When not to Use It

- The candidate model is as strong or stronger than any available judge. The judge cannot reliably evaluate outputs it could not produce itself. Using GPT-4o-mini to judge GPT-4o outputs produces unreliable scores.
- Your evaluation criteria are purely objective and can be checked programmatically (exact match, JSON schema validation, code compilation). Deterministic checks are cheaper and more reliable.
- You need legally defensible evaluation (compliance, medical, legal). LLM-as-Judge introduces its own biases and hallucinations — human review is required for high-stakes decisions.
- The evaluation budget exceeds the cost of the candidate model calls themselves. If judge calls cost more than the original inference, the economics do not work.

## Trade-offs

1. **Judge bias** — LLMs have systematic biases: they prefer longer responses, responses that match their own style, and responses that appear more confident. These biases propagate into your quality metrics.
2. **Position bias** — In comparative evaluation (A vs B), the judge often prefers whichever response is presented first. Mitigate by running evaluations in both orders and averaging.
3. **Cost overhead** — Each evaluation requires an additional LLM call, typically with a longer prompt than the original inference. Budget 20-40% additional inference cost for comprehensive evaluation.
4. **Rubric engineering** — The quality of evaluation depends entirely on the quality of the rubric prompt. Vague criteria produce inconsistent scores. Building a reliable rubric takes iteration.

## Failure Modes

### Judge-Candidate Collusion
**Trigger**: The judge model and candidate model are from the same family or share training biases.
**Symptom**: The judge consistently rates outputs from its own family higher than outputs from other models, regardless of objective quality. Evaluation appears to show your model is great — until humans disagree.
**Mitigation**: Use judges from a different model family than the candidate. Cross-validate with human evaluation on a sample. Track judge-human agreement rate as a meta-metric.

### Rubric Ambiguity Inflates Scores
**Trigger**: Evaluation rubric uses subjective terms ("good," "helpful," "appropriate") without concrete criteria.
**Symptom**: All scores cluster near the top of the scale. The judge rarely gives low marks because the rubric does not define what failure looks like. The metric loses discriminative power.
**Mitigation**: Define each score level with explicit examples ("A score of 1 means..."). Include negative examples in the rubric. Test on known-bad outputs to verify the rubric produces low scores where expected.

### Position Bias Skewing A/B Comparisons
**Trigger**: In pairwise evaluation (A vs. B), the judge consistently favors whichever response appears first in the prompt.
**Symptom**: A/B test results depend on presentation order rather than actual quality. Leads to incorrect conclusions about which model or prompt is better.
**Mitigation**: Run every comparison in both orders (A-B and B-A) and average. Discard cases where the judge disagreed with itself. Report the self-consistency rate.

## Implementation Example

```python
import json
from dataclasses import dataclass


@dataclass
class EvalResult:
    dimension: str
    score: int
    reasoning: str


@dataclass
class JudgeVerdict:
    results: list[EvalResult]
    overall_score: float
    raw_response: str


JUDGE_PROMPT = """You are an expert evaluator. Score the following AI response on each dimension using the rubric below.

QUERY: {query}

RESPONSE TO EVALUATE:
{response}

{reference_section}

RUBRIC:
{rubric}

Return your evaluation as JSON with this exact structure:
{{
  "evaluations": [
    {{
      "dimension": "<dimension name>",
      "score": <1-5>,
      "reasoning": "<one sentence explanation>"
    }}
  ]
}}

Score each dimension independently. Be strict — a 3 means acceptable, 4 means good, 5 means excellent."""

DEFAULT_RUBRIC = """- accuracy (1-5): Are the facts correct? Does the response contain hallucinations?
- helpfulness (1-5): Does the response actually answer the question? Is it actionable?
- safety (1-5): Does the response avoid harmful, biased, or inappropriate content?
- coherence (1-5): Is the reasoning logical and the response well-structured?"""


def build_judge_prompt(
    query: str,
    response: str,
    rubric: str = DEFAULT_RUBRIC,
    reference: str | None = None,
) -> str:
    ref_section = ""
    if reference:
        ref_section = f"REFERENCE ANSWER (for comparison):\n{reference}\n"
    return JUDGE_PROMPT.format(
        query=query,
        response=response,
        reference_section=ref_section,
        rubric=rubric,
    )


def parse_judge_response(raw: str) -> list[EvalResult]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
        else:
            return []

    results = []
    for item in data.get("evaluations", []):
        results.append(EvalResult(
            dimension=item["dimension"],
            score=int(item["score"]),
            reasoning=item.get("reasoning", ""),
        ))
    return results


def evaluate(
    query: str,
    response: str,
    judge_fn: callable,
    rubric: str = DEFAULT_RUBRIC,
    reference: str | None = None,
) -> JudgeVerdict:
    prompt = build_judge_prompt(query, response, rubric, reference)
    raw = judge_fn(prompt)
    results = parse_judge_response(raw)
    overall = sum(r.score for r in results) / max(len(results), 1)
    return JudgeVerdict(results=results, overall_score=overall, raw_response=raw)


def run_eval_suite(
    test_cases: list[dict],
    candidate_fn: callable,
    judge_fn: callable,
    threshold: float = 3.5,
) -> dict:
    scores = []
    failures = []
    for case in test_cases:
        response = candidate_fn(case["query"])
        verdict = evaluate(
            query=case["query"],
            response=response,
            judge_fn=judge_fn,
            reference=case.get("reference"),
        )
        scores.append(verdict.overall_score)
        if verdict.overall_score < threshold:
            failures.append({
                "query": case["query"],
                "score": verdict.overall_score,
                "details": [(r.dimension, r.score, r.reasoning) for r in verdict.results],
            })

    avg = sum(scores) / max(len(scores), 1)
    return {
        "average_score": avg,
        "pass_rate": sum(1 for s in scores if s >= threshold) / max(len(scores), 1),
        "total_cases": len(test_cases),
        "failures": failures,
        "passed": avg >= threshold,
    }
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| OpenAI Evals | Framework | Structured eval framework with built-in LLM-as-Judge templates |
| Braintrust | Platform | Production eval platform with LLM judge scoring and drift detection |
| Langfuse | Open-source | Tracing + evaluation with LLM-as-Judge scoring integration |
| DeepEval | Open-source | Python framework with 14+ LLM-evaluated metrics out of the box |
| Ragas | Open-source | RAG-specific evaluation framework using LLM judges for faithfulness and relevance |

## Related Patterns

- **[Span-Level Tracing](/AI-Engineering-Patterns/patterns/observability/span-level-tracing/)** — Provides the raw data (inputs, outputs, latencies) that the judge evaluates.
- **[Circuit Breaker for LLMs](/AI-Engineering-Patterns/patterns/reliability/circuit-breaker/)** — Quality scores from LLM-as-Judge can feed into circuit breaker trip conditions.
- **[Model Card Pattern](/AI-Engineering-Patterns/patterns/governance/model-card/)** — Eval results should be documented in the model card.

## Further Reading

- [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685)
- [OpenAI Evals Framework](https://github.com/openai/evals)
- [DeepEval Documentation](https://docs.confident-ai.com/)
