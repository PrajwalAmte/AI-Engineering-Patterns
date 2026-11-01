from loop_engineering.reflexion_loop import Memory, reflexion

TESTS = [((2, 3), 5), ((-1, 1), 0), ((0, 0), 0)]


def evaluate(code):
    """The evaluator is a real test run, not an opinion."""
    namespace = {}
    exec(code, namespace)  # test-only: we control every string executed here
    for args, expected in TESTS:
        got = namespace["add"](*args)
        if got != expected:
            return False, f"add{args} returned {got}, expected {expected}"
    return True, "all tests pass"


def actor(task, lessons):
    actor.seen.append(list(lessons))
    if any("negative" in lesson for lesson in lessons):
        return "def add(a, b):\n    return a + b"
    return "def add(a, b):\n    return abs(a) + abs(b)"


def reflect(task, attempt, feedback):
    return "Using abs() broke negative inputs; return a + b directly."


def test_lesson_from_a_failed_attempt_fixes_the_next_one():
    actor.seen = []
    result = reflexion("write add(a, b)", actor, evaluate, reflect)
    assert (result.passed, result.trials) == (True, 2)
    assert actor.seen == [[], ["Using abs() broke negative inputs; return a + b directly."]]


def test_same_lesson_twice_means_the_loop_is_not_learning():
    result = reflexion(
        "t",
        actor=lambda t, lessons: "def add(a, b):\n    return 0",
        evaluate=evaluate,
        reflect=lambda t, a, f: "Return the sum.",
        max_trials=10,
    )
    assert not result.passed
    assert result.trials == 2
    assert result.stop_reason.startswith("repeated lesson")


def test_memory_is_bounded_and_keeps_recent_lessons():
    m = Memory(max_lessons=2)
    for lesson in ["one", "two", "three"]:
        m.add(lesson)
    assert m.lessons == ["two", "three"]
    assert m.add("THREE ") is False
