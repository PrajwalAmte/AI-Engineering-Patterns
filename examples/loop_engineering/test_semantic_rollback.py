from loop_engineering.semantic_rollback import Step, run_workflow


def plan(state, attempt):
    return ["find vendors", "compare prices"]


def fetch_flaky(state, attempt):
    state["scratch"] = "partial download"  # side-state from a failed attempt must not survive
    if attempt == 1:
        raise TimeoutError("vendor API timed out")
    return {"acme": 49, "globex": 59}


def summarise(state, attempt):
    cheapest = min(state["fetch"], key=state["fetch"].get)
    return f"Cheapest is {cheapest}"


def test_failed_step_is_retried_from_the_last_checkpoint_and_completes():
    result = run_workflow([Step("plan", plan), Step("fetch", fetch_flaky), Step("summary", summarise)], {"task": "x"})
    assert result.completed
    assert result.state["summary"] == "Cheapest is acme"
    assert "fetch: attempt 1 rejected (TimeoutError: vendor API timed out); rolled back" in result.log


def test_invalid_output_is_rolled_back_even_without_an_exception():
    def fetch(state, attempt):
        state["junk"] = True
        return {} if attempt < 3 else {"acme": 49}

    result = run_workflow([Step("plan", plan), Step("fetch", fetch)], {})
    assert result.completed
    assert sum("rolled back" in line for line in result.log) == 2


def test_attempt_number_lets_a_step_change_strategy():
    tried = []

    def search(state, attempt):
        tried.append("broad query" if attempt == 1 else "narrow query")
        return [] if attempt == 1 else ["hit"]

    run_workflow([Step("search", search)], {})
    assert tried == ["broad query", "narrow query"]


def test_gives_up_after_max_attempts_with_the_last_good_state():
    def always_fails(state, attempt):
        raise ValueError("bad")

    result = run_workflow([Step("plan", plan), Step("fetch", always_fails)], {"task": "x"}, max_attempts=2)
    assert not result.completed
    assert result.failed_step == "fetch"
    assert result.state == {"task": "x", "plan": ["find vendors", "compare prices"]}
    assert "scratch" not in result.state
