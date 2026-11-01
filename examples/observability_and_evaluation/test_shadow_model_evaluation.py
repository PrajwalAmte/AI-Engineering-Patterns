import random

from observability_and_evaluation.shadow_model_evaluation import ShadowEvaluator, wilson_lower_bound


def prod(prompt, tools):
    return "prod:" + prompt


def make(candidate=None, judge=None, **kw):
    return ShadowEvaluator(
        production=prod,
        candidate=candidate or (lambda p, tools: "cand:" + p),
        judge=judge or (lambda p, a, b: "cand"),
        rng=random.Random(0),
        **kw,
    )


def test_users_always_get_the_production_answer():
    ev = make(sample_rate=1.0)
    assert ev.handle("hi") == "prod:hi"


def test_candidate_runs_with_tools_disabled():
    seen = []
    ev = make(candidate=lambda p, tools: seen.append(tools) or "x", sample_rate=1.0)
    ev.handle("send the invoice email")
    ev.drain()
    assert seen == [False]


def test_shadow_failures_never_reach_production():
    def broken(p, tools):
        raise RuntimeError("candidate endpoint down")

    ev = make(candidate=broken, sample_rate=1.0)
    for i in range(5):
        assert ev.handle(f"q{i}") == f"prod:q{i}"
    ev.drain()
    assert ev.tally.errors == 5


def test_full_queue_sheds_shadow_work():
    ev = make(sample_rate=1.0, max_queue=3)
    for i in range(10):
        ev.handle(str(i))
    assert ev.dropped == 7


def test_sampling_rate_is_respected():
    ev = make(sample_rate=0.2)
    for i in range(1000):
        ev.handle(str(i))
    assert 150 < ev._queue.qsize() < 250


def test_decision_needs_enough_data_and_a_clear_margin():
    ev = make(sample_rate=1.0)
    ev.tally.cand, ev.tally.prod = 60, 40
    assert ev.decision().startswith("keep shadowing")
    ev.tally.cand, ev.tally.prod = 130, 120
    assert ev.decision().startswith("no clear difference")
    ev.tally.cand, ev.tally.prod = 160, 90
    assert ev.decision().startswith("promote")
    ev.tally.cand, ev.tally.prod = 80, 170
    assert ev.decision().startswith("reject")


def test_wilson_bound_is_pessimistic():
    assert wilson_lower_bound(6, 10) < 0.35  # 6/10 is weak evidence
    assert wilson_lower_bound(600, 1000) > 0.56  # 600/1000 is strong evidence
