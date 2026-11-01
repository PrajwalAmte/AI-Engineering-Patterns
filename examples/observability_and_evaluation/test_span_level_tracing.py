import pytest

from common.fakes import FakeClock
from observability_and_evaluation.span_level_tracing import Tracer


def rag_request(tracer, clock, query, fail_rerank=False):
    with tracer.span("request", query=query) as root:
        with tracer.span("retrieve"):
            with tracer.span("embed"):
                clock.advance(0.05)
            with tracer.span("vector_search", k=20):
                clock.advance(0.10)
            with tracer.span("rerank"):
                clock.advance(0.30)
                if fail_rerank:
                    raise TimeoutError("reranker timed out")
        with tracer.span("llm", model="large", prompt="...context... " + query) as llm:
            clock.advance(1.5)
            tracer.set(llm, input_tokens=1800, output_tokens=200, cost_usd=0.012)
    return root.trace_id


def test_spans_nest_under_the_right_parents():
    clock = FakeClock()
    tracer = Tracer(clock=clock)
    trace_id = rag_request(tracer, clock, "how do refunds work")
    shape = [(depth, s.name) for depth, s in tracer.tree(trace_id)]
    assert shape == [
        (0, "request"),
        (1, "retrieve"),
        (2, "embed"),
        (2, "vector_search"),
        (2, "rerank"),
        (1, "llm"),
    ]


def test_rollup_answers_where_time_and_money_went():
    clock = FakeClock()
    tracer = Tracer(clock=clock)
    for q in ["a", "b"]:
        rag_request(tracer, clock, q)
    rollup = tracer.rollup()
    assert rollup["rerank"]["seconds"] == pytest.approx(0.6)
    assert rollup["llm"]["tokens"] == 4000
    assert rollup["llm"]["cost_usd"] == pytest.approx(0.024)


def test_errors_are_recorded_on_the_failing_span_and_still_raised():
    clock = FakeClock()
    tracer = Tracer(clock=clock)
    with pytest.raises(TimeoutError):
        rag_request(tracer, clock, "q", fail_rerank=True)
    failed = [s for s in tracer.finished if s.error]
    assert [s.name for s in failed] == ["rerank", "retrieve", "request"]


def test_prompts_are_hashed_not_stored_by_default():
    clock = FakeClock()
    tracer = Tracer(clock=clock)
    rag_request(tracer, clock, "my card number is 4111 1111 1111 1111")
    dump = repr([s.attributes for s in tracer.finished])
    assert "4111" not in dump
    assert "query.sha256" in dump


def test_dynamic_span_names_are_rejected():
    tracer = Tracer()
    with pytest.raises(ValueError):
        with tracer.span("llm-call-for-user-8812"):
            pass
