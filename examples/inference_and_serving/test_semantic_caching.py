from common.fakes import FakeClock, ScriptedLLM, embed
from inference_and_serving.semantic_caching import SemanticCache, cached_complete

SYSTEM = "You are the support assistant for Acme."


def make_cache(**kw):
    clock = FakeClock()
    return SemanticCache(embed=embed, threshold=0.8, clock=clock, **kw), clock


def test_rephrased_question_is_served_from_cache():
    cache, _ = make_cache()
    llm = ScriptedLLM(["Returns are accepted within 30 days."])
    cached_complete(cache, llm, "what is your return policy", SYSTEM, "acme")
    answer, hit = cached_complete(cache, llm, "What is your return policy?", SYSTEM, "acme")
    assert hit and answer == "Returns are accepted within 30 days."
    assert len(llm.calls) == 1


def test_unrelated_question_misses():
    cache, _ = make_cache()
    llm = ScriptedLLM(["a", "b"])
    cached_complete(cache, llm, "what is your return policy", SYSTEM, "acme")
    _, hit = cached_complete(cache, llm, "how do I reset my password", SYSTEM, "acme")
    assert not hit


def test_same_question_under_another_tenant_is_not_shared():
    cache, _ = make_cache()
    llm = ScriptedLLM(["acme answer", "globex answer"])
    cached_complete(cache, llm, "what is your return policy", SYSTEM, "acme")
    answer, hit = cached_complete(cache, llm, "what is your return policy", SYSTEM, "globex")
    assert not hit and answer == "globex answer"


def test_entries_expire():
    cache, clock = make_cache(ttl_s=60)
    llm = ScriptedLLM(["old", "new"])
    cached_complete(cache, llm, "what is your return policy", SYSTEM, "acme")
    clock.advance(61)
    assert cached_complete(cache, llm, "what is your return policy", SYSTEM, "acme") == ("new", False)


def test_changed_source_document_invalidates_dependent_answers():
    cache, _ = make_cache()
    scope = cache.scope_key(SYSTEM, "acme")
    cache.store("what is your return policy", "30 days", scope, sources={"policy.md"})
    assert cache.invalidate_source("policy.md") == 1
    assert cache.lookup("what is your return policy", scope) is None


def test_bad_answers_are_not_cached():
    cache, _ = make_cache()
    llm = ScriptedLLM(["", "real answer"])
    cached_complete(cache, llm, "what is your return policy", SYSTEM, "acme")
    assert cached_complete(cache, llm, "what is your return policy", SYSTEM, "acme") == ("real answer", False)
    assert cache.hit_rate == 0.0
