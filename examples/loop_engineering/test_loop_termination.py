from loop_engineering.loop_termination import run_loop


def scripted(outputs, cost=1.0):
    def step(i, last):
        return outputs[min(i - 1, len(outputs) - 1)], cost

    return step


def test_stops_on_success_as_soon_as_the_goal_is_met():
    out = run_loop(scripted(["draft", "better", "PASS"]), goal_met=lambda o: o == "PASS")
    assert (out.reason, out.iterations) == ("success", 3)


def test_success_on_the_final_allowed_iteration_is_still_success():
    out = run_loop(scripted(["a", "b", "PASS"]), goal_met=lambda o: o == "PASS", max_iterations=3)
    assert out.reason == "success"


def test_stalled_loop_stops_long_before_the_ceiling():
    out = run_loop(scripted(["try 1", "same fix", "same fix", "same fix"]), goal_met=lambda o: False, max_iterations=50)
    assert out.reason == "stalled"
    assert out.iterations < 6


def test_budget_ceiling_catches_cheap_but_endless_progress():
    outputs = [f"attempt number {i} with new content {i * 7}" for i in range(100)]
    out = run_loop(scripted(outputs, cost=0.25), goal_met=lambda o: False, max_cost=2.0)
    assert (out.reason, out.iterations) == ("budget", 8)


def test_iteration_ceiling_is_the_backstop():
    outputs = [f"genuinely different idea #{i}: " + "x" * i for i in range(30)]
    out = run_loop(scripted(outputs), goal_met=lambda o: False, max_iterations=5)
    assert (out.reason, out.iterations) == ("ceiling", 5)


def test_non_success_returns_best_result_not_last():
    outputs = ["score 3", "score 9", "score 3", "score 9", "score 3"]
    out = run_loop(scripted(outputs), goal_met=lambda o: False, score=lambda o: float(o.split()[1]))
    assert out.reason == "stalled"
    assert out.result == "score 9"
