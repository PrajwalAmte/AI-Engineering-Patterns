from governance.prompt_canary_deployment import STAGES, Rollout, Tolerance, bucket


def feed(rollout, n, canary_score=3.5, baseline_score=3.5, canary_flags=False, canary_tokens=500):
    for _ in range(n):
        rollout.baseline.add(baseline_score, False, False, 500)
        rollout.canary.add(canary_score, canary_flags, False, canary_tokens)


def test_bucketing_is_stable_and_roughly_uniform():
    assert bucket("user-1", "v2") == bucket("user-1", "v2")
    share = sum(bucket(f"u{i}", "v2") < 5 for i in range(10_000)) / 10_000
    assert 0.04 < share < 0.06


def test_users_stay_on_their_version_as_the_rollout_widens():
    r = Rollout("v1", "v2", Tolerance(min_samples=10))
    early = {u for u in (f"u{i}" for i in range(2000)) if r.version_for(u) == "v2"}
    feed(r, 10)
    r.evaluate()
    later = {u for u in (f"u{i}" for i in range(2000)) if r.version_for(u) == "v2"}
    assert early <= later and len(later) > len(early)


def test_healthy_canary_walks_through_every_stage():
    r = Rollout("v1", "v2", Tolerance(min_samples=10))
    for _ in STAGES:
        feed(r, 10)
        r.evaluate()
    assert r.state == "promoted" and r.percent == 100


def test_waits_for_enough_data_before_advancing():
    r = Rollout("v1", "v2", Tolerance(min_samples=100))
    feed(r, 20)
    assert r.evaluate() == "waiting for data"
    assert r.percent == 1


def test_quality_regression_rolls_back_once_significant():
    r = Rollout("v1", "v2", Tolerance(min_samples=50))
    feed(r, 20, canary_score=3.0)
    assert r.evaluate() == "waiting for data"
    feed(r, 40, canary_score=3.0)
    assert r.evaluate() == "rolled_back"
    assert r.percent == 0
    assert all(r.version_for(f"u{i}") == "v1" for i in range(100))


def test_safety_regression_rolls_back_immediately():
    r = Rollout("v1", "v2", Tolerance(min_samples=1000))
    feed(r, 5, canary_flags=True)
    assert r.evaluate() == "rolled_back"


def test_token_bloat_counts_as_a_regression():
    r = Rollout("v1", "v2", Tolerance(min_samples=10))
    feed(r, 10, canary_tokens=800)
    assert r.evaluate() == "rolled_back"
    assert "tokens" in r.history[-1]
