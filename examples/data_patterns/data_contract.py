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
