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
