import json

from common.fakes import ScriptedLLM
from observability_and_evaluation.llm_as_judge import agreement_with_humans, compare, score


def verdict(**kw):
    return json.dumps({"reasoning": "because", **kw})


def test_parses_score_even_with_chatter_around_the_json():
    judge = ScriptedLLM(["Sure! Here is my verdict:\n" + verdict(score=3) + "\nHope that helps."])
    assert score(judge, "q", "r") == 3


def test_out_of_range_or_malformed_verdicts_are_none_not_guessed():
    assert score(ScriptedLLM([verdict(score=9)]), "q", "r") is None
    assert score(ScriptedLLM(["I'd give it a solid B+"]), "q", "r") is None


def test_reference_answer_is_included_when_given():
    judge = ScriptedLLM([verdict(score=4)])
    score(judge, "capital of France?", "Paris", reference="Paris")
    assert "REFERENCE ANSWER" in judge.calls[0]


def test_pairwise_runs_both_orders_and_agrees():
    def judge(prompt):
        a = prompt.split("RESPONSE A:\n")[1].split("\n\nRESPONSE B")[0]
        return verdict(winner="A" if a == "good" else "B")

    assert compare(ScriptedLLM(judge), "q", "good", "bad") == "A"
    assert compare(ScriptedLLM(judge), "q", "bad", "good") == "B"


def test_position_biased_judge_produces_a_tie_not_a_winner():
    always_first = ScriptedLLM([verdict(winner="A")])
    assert compare(always_first, "q", "x", "y") == "tie"
    assert len(always_first.calls) == 2


def test_agreement_with_human_labels():
    labelled = [("q1", "r1", 4), ("q2", "r2", 2), ("q3", "r3", 1), ("q4", "r4", 3)]
    judge = ScriptedLLM([verdict(score=4), verdict(score=3), verdict(score=1), "garbage"])
    result = agreement_with_humans(judge, labelled)
    assert result.exact == 0.5
    assert result.within_one == 0.75
    assert result.unparseable == 1
