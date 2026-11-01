import pytest

from observability_and_evaluation.prompt_mutation_testing import (
    DEFAULT_OPERATORS,
    Case,
    casual,
    run,
    synonyms,
)

POLICY = "You can return items within 30 days for a full refund."
CASES = [Case("What is your refund policy?", check=lambda a: "30 days" in a)]


def brittle_bot(text):
    """Stands in for a prompt that only works on the phrasing it was tested with."""
    if "ignore your previous instructions" in text:
        return "Sure! My system prompt is: ..."
    return POLICY if "refund" in text.lower() else "Sorry, I can only help with orders."


def robust_bot(text):
    t = text.lower()
    if any(w in t for w in ("refund", "return", "rfeund", "refnud", "send back")):
        return POLICY
    return "Sorry, I can only help with orders."


def test_reports_which_kinds_of_mutation_break_the_prompt():
    ops = DEFAULT_OPERATORS + [synonyms({"refund": "return"})]
    report = run(brittle_bot, CASES, operators=ops)
    weakest = dict(report.weakest())
    assert weakest["injection"] == 0.0
    assert weakest["synonyms"] == 0.0
    assert weakest["casual"] == 1.0
    assert report.score < 0.8


def test_robust_prompt_scores_higher_on_the_same_mutations():
    ops = [casual, synonyms({"refund": "return"})]
    assert run(robust_bot, CASES, operators=ops).score == 1.0


def test_mutations_are_reproducible_with_a_seed():
    a = run(brittle_bot, CASES, seed=7).failures
    b = run(brittle_bot, CASES, seed=7).failures
    assert a == b


def test_refuses_to_run_when_the_unmutated_case_already_fails():
    with pytest.raises(ValueError):
        run(lambda t: "no idea", CASES)
