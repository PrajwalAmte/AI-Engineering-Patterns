from datetime import date

from common.fakes import embed
from data_patterns.semantic_deduplication import Doc, deduplicate


def test_reworded_copies_collapse_to_one_canonical_chunk():
    docs = [
        Doc("wiki-1", "To reset your password open Settings then Security and click Reset", "wiki", date(2025, 1, 1)),
        Doc("faq-7", "To reset your password, open Settings, then Security, and click Reset.", "faq", date(2026, 3, 1)),
        Doc("docs-3", "Invoices are emailed on the first business day of each month", "docs", date(2026, 1, 1)),
    ]
    canonical, merged = deduplicate(docs, embed, threshold=0.9)
    assert len(canonical) == 2
    assert merged == {"wiki-1": "faq-7"}  # newest wins by default


def test_authoritative_source_beats_recency():
    docs = [
        Doc("blog", "The API rate limit is 100 requests per minute per key", "blog", date(2026, 6, 1)),
        Doc("ref", "The API rate limit is 100 requests per minute per key.", "api-reference", date(2025, 1, 1)),
    ]
    canonical, _ = deduplicate(docs, embed, threshold=0.9, source_rank={"api-reference": 0, "blog": 5})
    assert [d.id for d in canonical] == ["ref"]


def test_near_identical_text_with_different_numbers_is_never_merged():
    docs = [
        Doc("us", "Standard shipping takes 5 business days", "policy", date(2026, 1, 1)),
        Doc("eu", "Standard shipping takes 10 business days", "policy", date(2026, 1, 1)),
    ]
    canonical, merged = deduplicate(docs, embed, threshold=0.5)
    assert len(canonical) == 2 and merged == {}


def test_merge_map_keeps_provenance_for_every_dropped_doc():
    text = "Refunds are processed within five business days"
    docs = [Doc(f"copy-{i}", text, "wiki", date(2026, 1, i + 1)) for i in range(4)]
    canonical, merged = deduplicate(docs, embed)
    assert len(canonical) == 1
    assert set(merged) | {canonical[0].id} == {d.id for d in docs}
