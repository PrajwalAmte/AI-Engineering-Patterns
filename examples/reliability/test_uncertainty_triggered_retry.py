from reliability.uncertainty_triggered_retry import Completion, answer, uncertainty


def model(*completions):
    calls = []
    queue = list(completions)

    def call(prompt):
        calls.append(prompt)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    call.calls = calls
    return call


def test_confident_answer_is_served_without_retry():
    base, strong = model(Completion("Paris.")), model(Completion("unused"))
    result = answer("Capital of France?", base, strong)
    assert (result.text, result.attempts, result.uncertain) == ("Paris.", 1, False)
    assert strong.calls == []


def test_hedging_answer_triggers_one_retry_on_the_stronger_model():
    base = model(Completion("I'm not sure, it might be Lyon, possibly Paris."))
    strong = model(Completion("Paris."))
    result = answer("Capital of France?", base, strong)
    assert (result.text, result.attempts, result.uncertain) == ("Paris.", 2, False)
    assert "Work through this carefully" in strong.calls[0]


def test_low_logprobs_count_even_without_hedging_words():
    shaky = Completion("The answer is 42.", token_logprobs=[-2.5, -3.0, -1.8])
    assert uncertainty(shaky) > 0.5
    steady = Completion("The answer is 42.", token_logprobs=[-0.01, -0.05, -0.02])
    assert uncertainty(steady) < 0.1


def test_incomplete_structured_output_is_maximally_uncertain():
    assert uncertainty(Completion('{"name": "Ada", "email": ""}'), ["name", "email"]) == 1.0
    assert uncertainty(Completion("not json"), ["name"]) == 1.0
    assert uncertainty(Completion('{"name": "Ada", "email": "a@b.c"}'), ["name", "email"]) == 0.0


def test_unsure_retry_is_surfaced_not_retried_again():
    base = model(Completion("I'm not sure."))
    strong = model(Completion("It's unclear from the information given."))
    result = answer("What was Q3 revenue?", base, strong)
    assert result.attempts == 2 and result.uncertain
    assert len(strong.calls) == 1
