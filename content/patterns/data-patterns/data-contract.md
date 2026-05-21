---
title: Data Contract Pattern
pillar: data-patterns
status: validated-in-production
tags: [data-quality, schema, contracts, pipelines]
related:
  - Feature Store Pattern
  - Data Observability Pattern
  - Training Data Pipeline Pattern
contributors: ["@PrajwalAmte"]
last_updated: "2026-03"
description: Schema, quality, and SLA agreements enforced as code between data producers and consumers to prevent upstream drift from breaking downstream AI.
sidebar:
  order: 1
---

## What It Is

A data contract is a formal, versioned agreement between a data producer and its consumers. It specifies the schema, data types, quality thresholds, freshness guarantees, and update frequency of a data source. Contracts are enforced as code in CI/CD pipelines, not as documentation that drifts out of sync.

## The Problem It Solves

AI systems depend on data pipelines owned by different teams. Without contracts, a team can rename a column, change a data type, or stop populating a field — and the first sign of a problem is degraded model quality in production. Silent schema drift is one of the most common and hardest-to-debug failure modes in production AI systems.

Specific failure scenarios:

- An upstream team renames `user_id` to `customer_id`. The feature pipeline breaks silently.
- A field that was always populated starts arriving as null 5% of the time. Model predictions degrade gradually.
- An upstream pipeline switches from daily to weekly updates. The freshness assumption in your RAG pipeline breaks.
- A categorical field gains new values the model was never trained on. Predictions become unreliable for those categories.

## How It Works

<pre class="mermaid">
flowchart TD
    A["Data producer team"] --> C["Define contract: schema, quality rules, SLA"]
    B["Data consumer team"] --> C
    C --> D["Version contract artifact"]
    D --> E["Producer CI validates outgoing data"]
    D --> F["Consumer CI validates incoming data"]
    E --> G{"Producer validation pass?"}
    F --> H{"Consumer validation pass?"}
    G -->|"No"| I["Block publish + alert"]
    H -->|"No"| J["Block ingest + alert"]
    G -->|"Yes"| K["Publish data"]
    H -->|"Yes"| L["Ingest data"]
    K --> M["Reliable downstream AI pipeline"]
    L --> M
</pre>

1. Producer and consumer teams agree on a contract definition (schema, quality rules, SLAs).
2. The contract is stored as a versioned artifact (YAML, JSON, or Protobuf) in a shared repository or registry.
3. The producer's CI pipeline validates outgoing data against the contract before publishing.
4. The consumer's pipeline validates incoming data against the contract before ingestion.
5. Contract violations trigger alerts and block bad data from propagating downstream.
6. Contract changes follow a versioning and deprecation protocol — breaking changes require a migration path.

## When to Use It

- Your AI system consumes data produced by other teams or external systems.
- You have experienced production incidents caused by upstream data changes.
- You need to enforce freshness, completeness, or type guarantees on data feeding models or retrieval systems.
- Multiple consumers depend on the same data source and need a shared quality bar.

## When not to Use It

- You own both the producer and consumer pipelines and they change together. In this case, schema enforcement in your own codebase is sufficient — a formal contract adds ceremony without value.
- Your data sources are ephemeral or experimental. Contracts assume stability. If the schema changes weekly during rapid iteration, contracts become a bottleneck.
- The data is consumed only by humans for exploration (dashboards, ad-hoc queries). Contracts are for machine consumers that break silently.

## Trade-offs

1. **Coordination overhead** — Establishing contracts requires cross-team agreement. This is valuable but time-consuming, especially in organizations without strong data governance.
2. **Rigidity** — Contracts resist change by design. Legitimate schema evolution becomes a multi-step process instead of a quick update.
3. **False sense of security** — A contract that validates schema but not data distribution gives confidence without catching the most common issues (value drift, null rate changes).
4. **Adoption challenge** — Contracts only work if producers actually run the validations. Without organizational commitment, they become ignored documentation.

## Failure Modes

### Schema Passes, Distribution Shifts
**Trigger**: Upstream data changes in value distribution (e.g., a field that was 5% null becomes 40% null) while still passing schema validation.
**Symptom**: Model quality degrades gradually. The contract reports green because types and required fields are correct, but the data is statistically different from what the model expects.
**Mitigation**: Add distribution-level assertions to contracts (null rate bounds, value range checks, cardinality thresholds). Use statistical tests, not just schema checks.

### Contract Versioning Deadlock
**Trigger**: A producer needs a breaking schema change, but multiple consumers depend on the current version with different migration timelines.
**Symptom**: Schema evolution stalls. Producer ships the change anyway (breaking consumers) or waits indefinitely (blocking their own roadmap). Either outcome damages trust in the contract system.
**Mitigation**: Define a deprecation policy upfront (e.g., old version supported for N weeks). Support running two schema versions in parallel during migration. Automate consumer compatibility checks.

### False Security from Selective Enforcement
**Trigger**: Contracts are defined but only enforced in CI — not at runtime in the data pipeline.
**Symptom**: A data issue that the contract would catch reaches production because the runtime path does not validate. Teams trust the contract and skip other defensive checks.
**Mitigation**: Enforce contracts at the pipeline ingestion boundary, not just in tests. Treat a contract violation in production as a P1 alert, not a logged warning.

## Implementation Example

```python
from dataclasses import dataclass

import yaml


@dataclass
class FieldContract:
    name: str
    dtype: str
    nullable: bool = False
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[str] | None = None
    max_null_rate: float = 0.0


@dataclass
class DataContract:
    name: str
    version: str
    owner: str
    fields: list[FieldContract]
    freshness_hours: int = 24
    min_row_count: int = 0

    @classmethod
    def from_yaml(cls, path: str) -> "DataContract":
        with open(path) as f:
            raw = yaml.safe_load(f)
        fields = [FieldContract(**f) for f in raw["fields"]]
        return cls(
            name=raw["name"],
            version=raw["version"],
            owner=raw["owner"],
            fields=fields,
            freshness_hours=raw.get("freshness_hours", 24),
            min_row_count=raw.get("min_row_count", 0),
        )


def validate_dataframe(df, contract: DataContract) -> list[str]:
    violations = []

    if len(df) < contract.min_row_count:
        violations.append(
            f"Row count {len(df)} below minimum {contract.min_row_count}"
        )

    for field in contract.fields:
        if field.name not in df.columns:
            violations.append(f"Missing required field: {field.name}")
            continue

        col = df[field.name]
        null_rate = col.isnull().mean()

        if not field.nullable and null_rate > 0:
            violations.append(f"{field.name}: contains nulls but is not nullable")
        elif null_rate > field.max_null_rate:
            violations.append(
                f"{field.name}: null rate {null_rate:.2%} exceeds max {field.max_null_rate:.2%}"
            )

        if field.min_value is not None:
            below = (col.dropna() < field.min_value).sum()
            if below > 0:
                violations.append(
                    f"{field.name}: {below} values below minimum {field.min_value}"
                )

        if field.allowed_values is not None:
            invalid = set(col.dropna().unique()) - set(field.allowed_values)
            if invalid:
                violations.append(
                    f"{field.name}: unexpected values {invalid}"
                )

    return violations
```

Contract definition (YAML):

```yaml
name: user_features
version: "2.1"
owner: data-platform-team
freshness_hours: 12
min_row_count: 10000
fields:
  - name: user_id
    dtype: string
    nullable: false
  - name: signup_days_ago
    dtype: int
    nullable: false
    min_value: 0
  - name: plan_type
    dtype: string
    nullable: false
    allowed_values: ["free", "pro", "enterprise"]
  - name: monthly_api_calls
    dtype: float
    nullable: true
    max_null_rate: 0.05
    min_value: 0
```

## Tool Landscape

| Tool | Type | Notes |
|---|---|---|
| Soda | Data quality platform | Contract-style checks with YAML definitions and CI integration |
| Great Expectations | Open-source library | Expectation-based data validation, widely adopted |
| dbt contracts | Built into dbt | Schema contracts enforced at the transformation layer |
| Dataform | Google Cloud | Schema assertions in the transformation pipeline |
| Protobuf/Avro | Schema registries | Strong typing for streaming data with schema evolution rules |

## Related Patterns

- **[Feature Store Pattern](/AI-Engineering-Patterns/patterns/data-patterns/feature-store/)** — Feature stores consume data that should be covered by contracts.
- **[Data Observability Pattern](/AI-Engineering-Patterns/patterns/data-patterns/data-observability/)** — Observability detects contract violations at runtime. Contracts define what "correct" means.
- **[Training Data Pipeline Pattern](/AI-Engineering-Patterns/patterns/data-patterns/training-data-pipeline/)** — Training pipelines need contracts on their input data sources.
- **[Eval Dataset Management](/AI-Engineering-Patterns/patterns/data-patterns/eval-dataset-management/)** — Eval datasets are themselves data artifacts that benefit from contract enforcement.

## Further Reading

- [Data Contracts — Andrew Jones](https://datacontract.com/)
- [Implementing Data Contracts at Scale — GoCardless Engineering](https://medium.com/gocardless-tech/implementing-data-contracts-at-gocardless-3ee4a4e3e9a6)
- [The Rise of Data Contracts — Chad Sanderson](https://dataproducts.substack.com/p/the-rise-of-data-contracts)
