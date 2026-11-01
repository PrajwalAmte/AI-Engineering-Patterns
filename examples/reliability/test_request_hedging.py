import asyncio

import pytest

from reliability.request_hedging import LatencyTracker, hedged_complete


def provider(text, seconds, log=None):
    async def call(prompt):
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            if log is not None:
                log.append("cancelled")
            raise
        return text

    return call


def run(coro):
    return asyncio.run(coro)


def tracker(delay):
    return LatencyTracker(default_s=delay)


def test_fast_primary_never_triggers_a_hedge():
    calls = []

    async def backup(prompt):
        calls.append(prompt)
        return "backup"

    result = run(hedged_complete("q", ("primary", provider("p", 0.01)), ("backup", backup), tracker(0.2)))
    assert (result.winner, result.hedged) == ("primary", False)
    assert calls == []


def test_slow_primary_is_beaten_by_backup_and_cancelled():
    log = []
    result = run(
        hedged_complete("q", ("primary", provider("p", 1.0, log)), ("backup", provider("b", 0.02)), tracker(0.05))
    )
    assert (result.winner, result.hedged) == ("backup", True)
    assert result.latency_s < 0.5
    assert log == ["cancelled"]


def test_primary_can_still_win_after_the_hedge_fires():
    result = run(
        hedged_complete("q", ("primary", provider("p", 0.08)), ("backup", provider("b", 1.0)), tracker(0.05))
    )
    assert (result.winner, result.hedged) == ("primary", True)


def test_fast_but_unacceptable_answer_is_not_taken():
    result = run(
        hedged_complete(
            "q",
            ("primary", provider("", 0.01)),
            ("backup", provider("real answer", 0.02)),
            tracker(0.5),
        )
    )
    assert result.winner == "backup"


def test_raises_when_nobody_answers_acceptably():
    with pytest.raises(RuntimeError):
        run(hedged_complete("q", ("a", provider("", 0.01)), ("b", provider("", 0.01)), tracker(0.05)))


def test_delay_follows_observed_p95():
    t = LatencyTracker(min_samples=20)
    for i in range(100):
        t.observe(1.0 if i < 95 else 9.0)
    assert t.delay() == 9.0
    assert LatencyTracker(default_s=2.0).delay() == 2.0
