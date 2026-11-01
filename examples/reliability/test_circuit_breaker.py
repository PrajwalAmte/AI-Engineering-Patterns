from common.fakes import FakeClock
from reliability.circuit_breaker import CircuitBreaker, State, complete


def failing(prompt):
    raise TimeoutError("provider timed out")


def fallback(prompt):
    return "fallback answer"


def make(clock, **kw):
    return CircuitBreaker(window=10, min_calls=4, cooldown_s=30, probes_to_close=2, clock=clock, **kw)


def test_trips_once_failure_rate_crosses_threshold():
    clock = FakeClock()
    breaker = make(clock)
    for _ in range(4):
        complete("q", failing, fallback, breaker, clock=clock)
    assert breaker.state is State.OPEN


def test_a_short_burst_below_min_calls_does_not_trip():
    clock = FakeClock()
    breaker = make(clock)
    for _ in range(3):
        complete("q", failing, fallback, breaker, clock=clock)
    assert breaker.state is State.CLOSED


def test_open_circuit_skips_the_primary_entirely():
    clock = FakeClock()
    breaker = make(clock)
    for _ in range(4):
        breaker.record(False)
    calls = []

    def primary(prompt):
        calls.append(prompt)
        return "primary answer"

    text, source = complete("q", primary, fallback, breaker, clock=clock)
    assert (text, source) == ("fallback answer", "fallback")
    assert calls == []


def test_half_open_probes_close_the_circuit_after_cooldown():
    clock = FakeClock()
    breaker = make(clock)
    for _ in range(4):
        breaker.record(False)
    clock.advance(30)
    assert breaker.state is State.HALF_OPEN
    breaker.record(True)
    breaker.record(True)
    assert breaker.state is State.CLOSED


def test_a_failed_probe_reopens_and_restarts_the_cooldown():
    clock = FakeClock()
    breaker = make(clock)
    for _ in range(4):
        breaker.record(False)
    clock.advance(30)
    breaker.record(False)
    assert breaker.state is State.OPEN
    clock.advance(29)
    assert breaker.state is State.OPEN


def test_slow_answers_are_returned_but_count_as_failures():
    clock = FakeClock()
    breaker = make(clock)

    def slow(prompt):
        clock.advance(12)
        return "slow but fine"

    for _ in range(4):
        text, source = complete("q", slow, fallback, breaker, latency_budget_s=10, clock=clock)
        assert source == "primary"
    assert breaker.state is State.OPEN


def test_empty_completion_falls_back_and_counts_as_failure():
    clock = FakeClock()
    breaker = make(clock)
    text, source = complete("q", lambda p: "   ", fallback, breaker, clock=clock)
    assert source == "fallback"
    assert list(breaker._results) == [False]
