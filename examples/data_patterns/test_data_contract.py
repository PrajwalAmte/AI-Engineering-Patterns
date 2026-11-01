from dataclasses import replace
from datetime import datetime, timedelta

from data_patterns.data_contract import Contract, Field, breaking_changes, ingest

NOW = datetime(2026, 11, 1, 12, 0)

TICKETS_V1 = Contract(
    name="support_tickets",
    version="1.0",
    fields=[
        Field("ticket_id", str),
        Field("body", str, max_null_rate=0.02),
        Field("priority", str, allowed=frozenset({"low", "normal", "high"})),
        Field("updated_at", datetime),
    ],
    max_staleness=timedelta(hours=6),
    timestamp_field="updated_at",
)


def rows(n=50, **overrides):
    base = {"ticket_id": "T1", "body": "printer on fire", "priority": "normal", "updated_at": NOW - timedelta(hours=1)}
    return [{**base, **overrides} for _ in range(n)]


def test_good_batch_is_accepted():
    assert ingest(rows(), TICKETS_V1, NOW).accepted


def test_renamed_column_is_caught():
    batch = [{("customer_ticket_id" if k == "ticket_id" else k): v for k, v in r.items()} for r in rows()]
    result = ingest(batch, TICKETS_V1, NOW)
    assert not result.accepted
    assert any("ticket_id: missing" in v for v in result.violations)


def test_null_rate_creep_is_caught_even_though_the_schema_allows_nulls():
    batch = rows(45) + rows(5, body=None)  # 10% nulls; contract allows 2%
    assert "body: null rate 10% > 2%" in ingest(batch, TICKETS_V1, NOW).violations


def test_new_category_value_is_caught():
    result = ingest(rows(priority="urgent"), TICKETS_V1, NOW)
    assert "priority: unexpected values ['urgent']" in result.violations


def test_stale_feed_is_caught():
    result = ingest(rows(updated_at=NOW - timedelta(days=2)), TICKETS_V1, NOW)
    assert any("older than" in v for v in result.violations)


def test_breaking_changes_are_detected_between_versions():
    v2 = replace(
        TICKETS_V1,
        version="2.0",
        fields=[
            Field("ticket_id", int),
            Field("body", str, max_null_rate=0.02),
            Field("priority", str, allowed=frozenset({"low", "normal", "high", "urgent"})),
            Field("updated_at", datetime),
            Field("tenant_id", str),
        ],
    )
    assert breaking_changes(TICKETS_V1, v2) == [
        "ticket_id: type str -> int",
        "priority: new allowed values",
        "new required field tenant_id",
    ]


def test_adding_an_optional_field_is_not_breaking():
    v1_1 = replace(TICKETS_V1, fields=TICKETS_V1.fields + [Field("tags", list, required=False, max_null_rate=1.0)])
    assert breaking_changes(TICKETS_V1, v1_1) == []
