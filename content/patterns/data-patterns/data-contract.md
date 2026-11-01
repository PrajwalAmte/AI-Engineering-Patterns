---
title: Data Contract
pillar: data-patterns
status: validated-in-production
tags: [data-quality, schema, contracts, pipelines]
related:
  - Semantic Deduplication
  - Retrieval Freshness Watermark
  - Embedding Drift Detector
example: examples/data_patterns/data_contract.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: An executable agreement about a dataset's schema, null rates, allowed values and freshness, checked by the producer before publishing and by the consumer before ingesting.
sidebar:
  order: 1
---

## What It Is

A data contract is a versioned file that says what a dataset promises: which fields exist and their types, how often each may be null, which values a categorical field can take, and how fresh the newest row must be. The important part is that it *runs*. The producer runs it in CI before publishing, the consumer runs it at the ingestion boundary, and a violation blocks the data instead of logging a warning nobody reads.

Data teams have used contracts for years. They matter more for AI systems because models and retrieval indexes fail quietly when their inputs change. Nothing crashes. Answers just get worse.

## The Problem It Solves

Your RAG index is built from the support team's ticket export, and the support team doesn't know your index exists. Over a quarter:

- They rename `ticket_id` to `customer_ticket_id`. Your join silently matches nothing.
- A form change makes `body` empty for 10% of tickets. Your schema allowed nulls, so nothing complained, and retrieval quality quietly drops.
- They add a priority value, `urgent`, that your routing logic has never seen.
- The export moves from hourly to daily. Your "current" answers are now a day old.

You find out about each one from a user complaint, weeks later.

## How It Works

<pre class="mermaid">
flowchart LR
    P["Producer"] --> PC["CI: validate sample<br/>+ breaking-change check vs last version"]
    PC -->|"pass"| PUB["Publish"]
    PC -->|"fail"| X1["Block release"]
    PUB --> CI["Consumer ingestion:<br/>validate every batch"]
    CI -->|"pass"| D["Index / features / training"]
    CI -->|"fail"| X2["Quarantine batch + page owner"]
    K["contract.yaml<br/>(versioned, owned by both)"] -.-> PC & CI
</pre>

1. **Write the contract together.** The consumer says what it depends on, and the producer says what it can promise. Store the contract in version control next to the producer's code.
2. **Go beyond types.** A schema check alone catches renames and type changes. Null-rate bounds, allowed values and freshness catch the failures that actually hurt models.
3. **Check compatibility in the producer's CI.** Compare the new contract with the last one. Removed fields, type changes, looser null rates and new enum values are breaking, and need a new major version and a migration window.
4. **Validate at ingestion.** Each batch is checked before anything downstream sees it. Failed batches go to quarantine, and the last good data keeps serving.

## When to Use It

- Your AI system consumes data owned by another team or an external system.
- An upstream change has already caused an incident.
- Several consumers depend on the same source and should share one definition of "correct".

## When NOT to Use It

- **You own both sides and ship them together.** Validate in your own code. A formal contract between you and yourself is ceremony.
- **The schema changes weekly during exploration.** Contracts assume some stability. Add them once the source settles.
- **Only humans read the data,** in dashboards or ad-hoc analysis. People notice when a chart looks wrong. Pipelines don't.

## Trade-offs

- **Coordination.** A contract is an agreement between teams, so someone has to negotiate it and someone has to own it. That's the point, but it costs time.
- **Deliberate friction.** Breaking changes now need a version bump and a migration window, which slows the producer down.
- **False confidence from thin contracts.** A contract that only checks types makes dashboards green while the data rots. Distribution checks are where the value is.

## Failure Modes

**Schema passes, distribution shifts.** The types are right, but `body` went from 1% null to 40%, or the average document length halved. Add null-rate and value-range bounds. For embeddings, also watch the distribution itself ([Embedding Drift Detector](../observability-and-evaluation/embedding-drift-detector.md)).

**Contracts only run in CI.** CI validates a fixture file. Production ingests whatever arrives. Validate at the runtime boundary too.

**Version deadlock.** The producer needs a breaking change, one consumer can migrate this week and another next quarter. Agree on a deprecation policy before you need it (for example, publish both versions for N weeks).

## Implementation Example

Field-level checks (presence, type, null rate, allowed values), a freshness check, a breaking-change diff between versions, and a consumer-side ingest gate. The tests walk through each of the four upstream changes described above.

```bash
cd examples && pytest data_patterns/test_data_contract.py
```

<!-- example: examples/data_patterns/data_contract.py -->
```python
"""Data Contract.

A versioned, executable agreement about a dataset: its schema, how much of it
may be missing, which values are allowed, and how fresh it must be. The same
contract runs in the producer's CI (before publishing) and at the consumer's
ingestion boundary (before anything downstream sees the data). A second check
compares two contract versions and says whether the change is breaking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Field:
    name: str
    type: type
    required: bool = True
    max_null_rate: float = 0.0  # schema says "nullable"; this says "how often"
    allowed: frozenset | None = None


@dataclass
class Contract:
    name: str
    version: str
    fields: list[Field]
    max_staleness: timedelta | None = None
    timestamp_field: str | None = None

    def validate(self, rows: list[dict], now: datetime) -> list[str]:
        violations: list[str] = []
        if not rows:
            return [f"{self.name}: batch is empty"]

        for f in self.fields:
            values = [row.get(f.name) for row in rows]
            if f.required and any(f.name not in row for row in rows):
                violations.append(f"{f.name}: missing from some rows")
            nulls = sum(v is None for v in values)
            if nulls / len(rows) > f.max_null_rate:
                violations.append(f"{f.name}: null rate {nulls / len(rows):.0%} > {f.max_null_rate:.0%}")
            wrong_type = [v for v in values if v is not None and not isinstance(v, f.type)]
            if wrong_type:
                violations.append(f"{f.name}: expected {f.type.__name__}, got {type(wrong_type[0]).__name__}")
            if f.allowed is not None:
                unknown = {v for v in values if v is not None} - f.allowed
                if unknown:
                    violations.append(f"{f.name}: unexpected values {sorted(map(str, unknown))}")

        if self.max_staleness and self.timestamp_field:
            stamps = [row[self.timestamp_field] for row in rows if row.get(self.timestamp_field)]
            if not stamps or now - max(stamps) > self.max_staleness:
                violations.append(f"{self.name}: newest row older than {self.max_staleness}")
        return violations


def breaking_changes(old: Contract, new: Contract) -> list[str]:
    """What would break a consumer written against `old`? Run this in the producer's CI."""
    changes = []
    before = {f.name: f for f in old.fields}
    after = {f.name: f for f in new.fields}
    for name, f in before.items():
        if name not in after:
            changes.append(f"removed field {name}")
            continue
        g = after[name]
        if g.type is not f.type:
            changes.append(f"{name}: type {f.type.__name__} -> {g.type.__name__}")
        if g.max_null_rate > f.max_null_rate:
            changes.append(f"{name}: may now be null more often")
        if f.allowed is not None and (g.allowed is None or not g.allowed <= f.allowed):
            changes.append(f"{name}: new allowed values")  # consumers may not handle them
    for name, g in after.items():
        if name not in before and g.required:
            changes.append(f"new required field {name}")  # breaks producers of the old shape
    return changes


@dataclass
class IngestResult:
    accepted: bool
    violations: list[str] = field(default_factory=list)


def ingest(rows: list[dict], contract: Contract, now: datetime) -> IngestResult:
    """Consumer-side gate: a violation blocks the batch instead of logging a warning."""
    violations = contract.validate(rows, now)
    return IngestResult(accepted=not violations, violations=violations)
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Data Contract Specification + CLI | Open YAML spec, with a CLI that tests data against it and diffs versions |
| dbt model contracts | Enforce column names and types at build time in dbt |
| Soda, Great Expectations | Data quality checks (null rates, ranges, freshness) as code |
| Confluent Schema Registry (Avro/Protobuf) | Compatibility rules for streaming schemas |

## Related Patterns

- [Semantic Deduplication](semantic-deduplication.md) runs right after a batch passes its contract and before indexing.
- [Retrieval Freshness Watermark](../retrieval-and-memory/retrieval-freshness-watermark.md) needs reliable effective dates, and the contract is where you require them.
- [Embedding Drift Detector](../observability-and-evaluation/embedding-drift-detector.md) catches the drift a contract can't express.

## Further Reading

- [Data Contract Specification](https://datacontract.com/)
- [The Rise of Data Contracts](https://dataproducts.substack.com/p/the-rise-of-data-contracts), Chad Sanderson
- *Driving Data Quality with Data Contracts*, Andrew Jones (Packt, 2023)
