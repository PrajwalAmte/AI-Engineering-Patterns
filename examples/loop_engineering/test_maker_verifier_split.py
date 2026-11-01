import json

from loop_engineering.maker_verifier_split import Attempt, Verdict, all_of, run

CRITERIA = "JSON object with string 'name' and integer 'age' >= 0"


def is_json(o):
    try:
        json.loads(o)
    except json.JSONDecodeError:
        return "output is not valid JSON"
    return None


def has_fields(o):
    try:
        d = json.loads(o)
    except json.JSONDecodeError:
        return None
    if not isinstance(d.get("age"), int) or d["age"] < 0:
        return "age must be a non-negative integer"
    if not isinstance(d.get("name"), str):
        return "name must be a string"
    return None


VERIFY = all_of(is_json, has_fields)


def maker_that_learns():
    outputs = iter(['{"name": "Ada", "age": "36"}', '{"name": "Ada", "age": 36}'])

    def make(task, issues):
        make.seen_issues.append(list(issues))
        return Attempt(next(outputs), rationale="I am confident this is correct.")

    make.seen_issues = []
    return make


def test_rejection_reasons_reach_the_maker_and_fix_it():
    maker = maker_that_learns()
    result = run("extract person", CRITERIA, maker, VERIFY)
    assert (result.status, result.rounds) == ("verified", 2)
    assert maker.seen_issues == [[], ["age must be a non-negative integer"]]


def test_verifier_never_sees_the_makers_reasoning():
    seen = []

    def verifier(criteria, output):
        seen.append(output)
        return Verdict(True)

    run("t", CRITERIA, lambda t, i: Attempt("out", rationale="trust me, it's done"), verifier)
    assert seen == ["out"]


def test_repeated_rejection_escalates_to_a_human():
    result = run("t", CRITERIA, lambda t, i: Attempt("not json"), VERIFY, max_rounds=3)
    assert (result.status, result.rounds) == ("escalated", 3)


def test_uncertain_verifier_escalates_instead_of_guessing():
    result = run("t", CRITERIA, lambda t, i: Attempt("{}"), lambda c, o: Verdict(False, uncertain=True))
    assert (result.status, result.rounds) == ("escalated", 1)
