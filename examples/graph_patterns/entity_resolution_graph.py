"""Entity Resolution Graph.

Decide which records from different sources are the same real-world entity.
Records are nodes; an edge means "probably the same". Clusters are connected
components, with one safeguard that plain connected components lacks: a
cluster is never allowed to contain two records with *conflicting* strong
identifiers (different emails, different tax IDs). That stops one fuzzy edge
from chaining two different companies together.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

SUFFIXES = re.compile(r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|gmbh|plc)\b\.?", re.I)


@dataclass
class Record:
    id: str
    source: str
    name: str
    email_domain: str | None = None
    tax_id: str | None = None
    city: str | None = None


def normalize(name: str) -> str:
    name = SUFFIXES.sub("", name.lower().replace("&", " and "))
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", name)).strip()


def tokens(name: str) -> set[str]:
    return set(normalize(name).split())


def score(a: Record, b: Record) -> float:
    """0-1 match score from name overlap plus agreeing attributes."""
    ta, tb = tokens(a.name), tokens(b.name)
    name = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    bonus = 0.0
    if a.email_domain and a.email_domain == b.email_domain:
        bonus += 0.4
    if a.city and a.city == b.city:
        bonus += 0.1
    if a.tax_id and a.tax_id == b.tax_id:
        return 1.0
    return min(1.0, name * 0.7 + bonus)


def _conflict(a: Record, b: Record) -> bool:
    return bool(
        (a.tax_id and b.tax_id and a.tax_id != b.tax_id)
        or (a.email_domain and b.email_domain and a.email_domain != b.email_domain)
    )


def blocks(records: list[Record]) -> dict[str, list[Record]]:
    """Only compare records sharing a name token, so cost isn't O(n²) over everything."""
    out: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        for t in tokens(r.name):
            if len(t) > 2:
                out[t].append(r)
    return out


@dataclass
class Resolution:
    clusters: list[list[Record]]
    edges: list[tuple[str, str, float]] = field(default_factory=list)
    rejected: list[tuple[str, str, str]] = field(default_factory=list)  # merges blocked by conflicts


def resolve(records: list[Record], threshold: float = 0.6) -> Resolution:
    by_id = {r.id: r for r in records}
    candidate_pairs = set()
    for group in blocks(records).values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                candidate_pairs.add(tuple(sorted((a.id, b.id))))

    scored = sorted(
        ((score(by_id[a], by_id[b]), a, b) for a, b in candidate_pairs), reverse=True
    )  # strongest evidence merges first
    cluster_of = {r.id: {r.id} for r in records}
    result = Resolution([])
    for s, a, b in scored:
        if s < threshold or cluster_of[a] is cluster_of[b]:
            continue
        ca, cb = cluster_of[a], cluster_of[b]
        clash = next(((x, y) for x in ca for y in cb if _conflict(by_id[x], by_id[y])), None)
        if clash:
            result.rejected.append((a, b, f"conflicting identifiers between {clash[0]} and {clash[1]}"))
            continue
        merged = ca | cb
        for rid in merged:
            cluster_of[rid] = merged
        result.edges.append((a, b, round(s, 2)))

    unique = {id(c): c for c in cluster_of.values()}.values()
    result.clusters = [sorted((by_id[i] for i in c), key=lambda r: r.id) for c in unique]
    return result
