from common.fakes import ScriptedLLM
from inference_and_serving.model_router import ModelRouter, Tier, complexity_score


def make_router(small=None, large=None, accept=None):
    small = small or ScriptedLLM(["small answer"])
    large = large or ScriptedLLM(["large answer"])
    router = ModelRouter(tiers=[Tier("small", small, max_score=0.3), Tier("large", large, max_score=1.0)])
    if accept:
        router.accept = accept
    return router, small, large


def test_lookup_questions_score_low_and_reasoning_scores_high():
    assert complexity_score("What is the capital of France?") < 0.3
    assert complexity_score("Explain the trade-offs and design a migration plan step by step") > 0.5


def test_simple_query_goes_to_the_cheap_tier():
    router, small, large = make_router()
    assert router.answer("What time zone is Tokyo in?") == ("small answer", "small")
    assert large.calls == []


def test_hard_query_skips_the_cheap_tier():
    router, small, large = make_router()
    answer, tier = router.answer("Why does this deadlock? Debug it:\n```\ndef worker(): ...\n```")
    assert tier == "large"
    assert small.calls == []


def test_rejected_cheap_answer_escalates_and_is_counted():
    router, small, large = make_router(
        small=ScriptedLLM(["I don't know"]),
        accept=lambda q, a: "don't know" not in a,
    )
    assert router.answer("Who wrote Dune?") == ("large answer", "large")
    assert router.stats["escalated_from:small"] == 1
    assert router.stats["routed:small"] == 1
