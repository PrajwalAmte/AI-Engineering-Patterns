from datetime import date

from retrieval_and_memory.retrieval_freshness_watermark import Chunk, build_context, freshness, rank

TODAY = date(2026, 11, 1)


def test_superseded_version_is_dropped_even_if_more_similar():
    old = Chunk("pricing-page", "Pro is $39/month", date(2025, 1, 1), "pricing")
    new = Chunk("pricing-page", "Pro is $49/month", date(2026, 9, 1), "pricing")
    ranked = rank("how much is Pro", [(old, 0.95), (new, 0.80)], TODAY)
    assert [c.text for c, _ in ranked] == ["Pro is $49/month"]


def test_revoked_content_is_never_served():
    revoked = Chunk("old-faq", "Refunds within 90 days", date(2026, 1, 1), "policy", expired=True)
    assert rank("refund window", [(revoked, 0.99)], TODAY) == []


def test_freshness_decays_by_content_type_with_a_floor():
    news = Chunk("n", "x", date(2026, 10, 18), "news")  # one half-life old
    assert abs(freshness(news, TODAY) - 0.5) < 0.01
    ancient = Chunk("a", "x", date(2000, 1, 1), "news")
    assert freshness(ancient, TODAY) == 0.2


def test_age_only_matters_for_time_sensitive_queries():
    stale = Chunk("tls-old", "TLS handshake explained", date(2019, 1, 1), "news")
    fresh = Chunk("tls-new", "TLS handshake overview", date(2026, 10, 30), "news")
    timeless = rank("how does the TLS handshake work", [(stale, 0.90), (fresh, 0.85)], TODAY)
    assert timeless[0][0] is stale
    current = rank("what is the latest TLS handshake guidance", [(stale, 0.90), (fresh, 0.85)], TODAY)
    assert current[0][0] is fresh


def test_context_tells_the_model_how_old_each_source_is():
    chunk = Chunk("p", "Pro is $49/month", date(2026, 9, 1), "pricing")
    context = build_context([(chunk, 1.0)], TODAY)
    assert "[1] (as of 2026-09-01, 61 days old) Pro is $49/month" in context
    assert "Today is 2026-11-01" in context
