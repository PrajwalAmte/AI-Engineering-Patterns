from common.fakes import ScriptedLLM
from graph_patterns.graph_of_thoughts import GraphOfThoughts

TARGET = [1, 2, 3, 4, 5, 6, 7, 8]


def parse(text):
    return [int(x) for x in text.split()] if text.strip() else []


def sorted_fraction(text):
    """Programmatic scorer: share of TARGET placed correctly."""
    nums = parse(text)
    return sum(a == b for a, b in zip(nums, TARGET)) / len(TARGET)


def sorter(prompt):
    """Stands in for an LLM that sorts halves well but can't do the whole list in one go."""
    op, rest = prompt.split("\n", 1)
    if op.startswith("GENERATE"):
        i = int(op.split("#")[1])
        return ["1 2 3 4 8 7 6 5", "4 3 2 1 5 6 7 8", "2 1 3 4 6 5 7 8"][i]
    if op == "AGGREGATE":
        candidates = [parse(c) for c in rest.split("\n", 1)[1].split("\n---\n")]
        merged = candidates[0][:4] + candidates[1][4:]  # take each candidate's better half
        return " ".join(map(str, merged))
    if op == "REFINE":
        return rest.split("\n", 1)[1]  # no-op refine, so any improvement is the aggregation's
    return ""


def test_aggregation_combines_the_good_parts_of_different_branches():
    got = GraphOfThoughts(ScriptedLLM(sorter), sorted_fraction, branches=3, keep=2)
    best = got.solve("sort: 5 3 8 1 4 7 2 6")
    assert parse(best.text) == TARGET
    assert best.score == 1.0


def test_lineage_shows_how_the_answer_was_built():
    got = GraphOfThoughts(ScriptedLLM(sorter), sorted_fraction)
    best = got.solve("sort")
    ops = [line.split()[1] for line in got.lineage(best)]
    assert "aggregate" in ops and "generate" in ops


def test_stops_early_when_a_branch_is_already_good_enough():
    llm = ScriptedLLM(lambda p: " ".join(map(str, TARGET)))
    got = GraphOfThoughts(llm, sorted_fraction, branches=2)
    got.solve("sort")
    assert len(llm.calls) == 2


def test_call_budget_is_respected_and_best_so_far_is_returned():
    llm = ScriptedLLM(lambda p: "8 7 6 5 4 3 2 1")
    got = GraphOfThoughts(llm, sorted_fraction, branches=3, max_rounds=10, max_calls=5)
    best = got.solve("sort")
    assert len(llm.calls) == 5
    assert best is not None
