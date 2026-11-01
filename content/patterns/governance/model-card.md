---
title: Model Card
pillar: governance
status: validated-in-production
tags: [governance, documentation, compliance, evaluation]
related:
  - Human-in-the-Loop
  - Prompt Canary Deployment
  - LLM-as-Judge
  - Data Contract
example: examples/governance/model_card.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: Document each AI feature's intended use, limits, data and evals as data next to the code, and fail CI when the card is incomplete or its evals are stale.
sidebar:
  order: 3
---

## What It Is

Model cards come from Mitchell et al. (2019): a short, standard document describing what a model is for, what it isn't for, how it was evaluated, and where it falls short. This page adapts the idea in two ways for teams shipping LLM features:

1. **Card the system, not just the model.** Users experience "the support bot", which is a base model, a prompt version, retrieval sources and guardrails together. That's the unit to document.
2. **Make the card executable.** It lives in the repo as data, gets rendered to markdown, and CI fails when it's incomplete or out of date. A wiki page goes stale within a quarter. A failing build gets attention.

## The Problem It Solves

Ask a team "what is this assistant *not* supposed to do?", "when was it last evaluated?" or "which model version is in production?" and you often get three different answers, or none. Then:

- A product manager launches it to a use case it was never evaluated for.
- An auditor or enterprise customer asks for documentation, and someone spends a week reconstructing it.
- A model alias changes underneath you, and the "evaluation results" on the wiki describe a model that's no longer running.

## How It Works

<pre class="mermaid">
flowchart LR
    C["card.py / card.yaml<br/>(in the repo)"] --> V{"CI checks"}
    V -->|"empty sections"| F["Fail"]
    V -->|"model is an alias"| F
    V -->|"evals older than last change<br/>or older than 90 days"| F
    V -->|"ok"| R["Render markdown → docs site / customer packet"]
</pre>

1. **Describe the system:** owner, pinned base model version, prompt version, data sources, and the human oversight in place.
2. **State intended use and out-of-scope uses** in plain words. The out-of-scope list is usually the most valuable part.
3. **List known limitations** honestly ("English only", "articles over 90 days old may be stale"). An empty list means nobody looked.
4. **Attach eval results** with the dataset, metric, value and date.
5. **Let CI enforce freshness.** Evals must postdate the last model or prompt change, and must not be older than your policy allows.

## When to Use It

- Any AI feature used by customers or by other teams.
- Enterprise sales or regulated settings (the EU AI Act, NIST AI RMF and sector rules all ask for this kind of documentation).
- More than one AI feature in production, so people need a consistent place to look.

## When NOT to Use It

- **Prototypes and internal experiments.** A README is enough until real users depend on it.
- **As a substitute for evals.** A card *reports* evaluation. If the evals don't exist, the card should fail, not paper over it.

## Trade-offs

- **Upkeep.** Every model or prompt change means updating evals and the card. Automating the freshness check is what makes this affordable.
- **Honesty versus marketing.** Limitations sections tend to get softened before external release. Keep an internal version that says it plainly.
- **Scope creep.** Cards grow into long questionnaires that nobody reads. Keep the required fields few and meaningful.

## Failure Modes

**Card from launch day, never updated.** It describes the model from eighteen months ago. CI freshness checks against the last change date prevent this.

**Aliases instead of versions.** "Model: gpt-4o" or "claude-sonnet-latest" says nothing about what actually ran. Require pinned version identifiers.

**Evals with no lineage.** "Accuracy 94%" on an unnamed dataset can't be reproduced or compared. Name the dataset and version, and keep the eval code in the repo.

## Implementation Example

A model card as a dataclass, with CI checks for empty sections, aliased model names, evals older than the last change, and evals past a maximum age, plus a markdown renderer for docs and customer packets.

```bash
cd examples && pytest governance/test_model_card.py
```

<!-- example: examples/governance/model_card.py -->
```python
"""Model Card, as a CI check.

The card lives next to the code as data, not as a wiki page. CI renders it to
markdown and fails the build when it's incomplete or stale: missing intended
use, no stated limitations, no eval results, or evals older than the model or
prompt they describe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class EvalResult:
    name: str
    metric: str
    value: float
    run_on: date
    dataset: str


@dataclass
class ModelCard:
    system: str  # the AI feature, not just the base model
    owner: str
    base_model: str  # pinned version, not an alias
    prompt_version: str
    changed_on: date  # when base_model or prompt_version last changed
    intended_use: list[str]
    out_of_scope: list[str]
    limitations: list[str]
    data_sources: list[str]
    evals: list[EvalResult] = field(default_factory=list)
    human_oversight: str = ""

    def problems(self, today: date, max_eval_age_days: int = 90) -> list[str]:
        out = []
        for name in ("intended_use", "out_of_scope", "limitations", "data_sources"):
            if not getattr(self, name):
                out.append(f"{name} is empty")
        if self.base_model.endswith(("latest", "-preview")) or self.base_model.count("-") < 1:
            out.append(f"base_model {self.base_model!r} looks like an alias; pin a version")
        if not self.evals:
            out.append("no eval results")
        for e in self.evals:
            if e.run_on < self.changed_on:
                out.append(f"eval {e.name!r} predates the last model/prompt change")
            if (today - e.run_on).days > max_eval_age_days:
                out.append(f"eval {e.name!r} is older than {max_eval_age_days} days")
        if not self.human_oversight:
            out.append("human_oversight not described")
        return out

    def to_markdown(self) -> str:
        bullets = lambda items: "\n".join(f"- {i}" for i in items)  # noqa: E731
        rows = "\n".join(
            f"| {e.name} | {e.metric} | {e.value:.3g} | {e.dataset} | {e.run_on.isoformat()} |" for e in self.evals
        )
        return f"""# Model card: {self.system}

**Owner:** {self.owner} · **Model:** `{self.base_model}` · **Prompt:** `{self.prompt_version}`

## Intended use
{bullets(self.intended_use)}

## Out of scope
{bullets(self.out_of_scope)}

## Known limitations
{bullets(self.limitations)}

## Data sources
{bullets(self.data_sources)}

## Evaluation
| Eval | Metric | Value | Dataset | Run on |
|---|---|---|---|---|
{rows}

## Human oversight
{self.human_oversight}
"""
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Hugging Face model cards | The most widely used format for model weights |
| Google Model Card Toolkit | Structured schema and rendering |
| Provider system cards | Anthropic, OpenAI and Google publish cards for their models; reference them from yours |

## Related Patterns

- [Human-in-the-Loop](human-in-the-loop.md) is described in the card's oversight section.
- [Prompt Canary Deployment](prompt-canary-deployment.md): each promotion should update the card's prompt version and eval date.
- [LLM-as-Judge](../observability-and-evaluation/llm-as-judge.md) produces many of the eval numbers the card reports.
- [Data Contract](../data-patterns/data-contract.md) documents the data sources the card lists.

## Further Reading

- [Model Cards for Model Reporting](https://arxiv.org/abs/1810.03993), Mitchell et al., 2019
- [Hugging Face model card guide](https://huggingface.co/docs/hub/model-cards)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
