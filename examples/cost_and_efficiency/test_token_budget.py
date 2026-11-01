import pytest

from cost_and_efficiency.token_budget import Budget, OverBudget, assemble


def count(text):
    return len(text.split())


SMALL = Budget(context_window=100, reserve_output=20, system=10, history=20, retrieved=30, user=15)


def words(n, tag="w"):
    return " ".join([tag] * n)


def test_keeps_most_relevant_chunks_that_fit():
    chunks = [(words(15, "low"), 0.2), (words(15, "high"), 0.9), (words(15, "mid"), 0.5)]
    result = assemble("sys", [], chunks, "question?", SMALL, count)
    assert [c.split()[0] for c in result.chunks] == ["high", "mid"]
    assert result.dropped["chunks"] == 1


def test_keeps_most_recent_history_in_original_order():
    history = [words(8, "t1"), words(8, "t2"), words(8, "t3")]
    result = assemble("sys", history, [], "q", SMALL, count)
    assert [h.split()[0] for h in result.history] == ["t2", "t3"]
    assert result.dropped["turns"] == 1


def test_output_is_always_reserved():
    result = assemble("sys", [], [(words(30), 1.0)], "q", SMALL, count)
    assert result.tokens["reserved_output"] == 20
    assert sum(v for k, v in result.tokens.items() if k != "reserved_output") <= 80


def test_never_truncates_system_prompt_or_user_input():
    with pytest.raises(OverBudget, match="system prompt"):
        assemble(words(11), [], [], "q", SMALL, count)
    with pytest.raises(OverBudget, match="user input"):
        assemble("sys", [], [], words(16), SMALL, count)


def test_misconfigured_budgets_are_caught():
    bad = Budget(context_window=50, reserve_output=20, system=10, history=20, retrieved=30, user=15)
    with pytest.raises(OverBudget, match="add up"):
        assemble(words(10), [words(20)], [(words(30), 1.0)], words(10), bad, count)
