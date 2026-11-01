from common.fakes import ScriptedLLM
from retrieval_and_memory.grounding_verifier import extract_claims, verify

SOURCES = [
    "The Pro plan costs $49 per month and includes 10 seats.",
    "Annual billing gives a 20% discount on any plan.",
]


def test_supported_claims_get_citations():
    result = verify("The Pro plan costs $49 per month.", SOURCES)
    assert result.ungrounded == []
    assert result.text == "The Pro plan costs $49 per month. [1]"


def test_wrong_number_is_ungrounded_even_with_word_overlap():
    result = verify("The Pro plan costs $59 per month.", SOURCES)
    assert result.ungrounded == ["The Pro plan costs $59 per month."]
    assert "[unverified]" in result.text


def test_invented_detail_is_caught_alongside_a_grounded_one():
    response = "Annual billing gives a 20% discount. The Pro plan includes a dedicated account manager."
    result = verify(response, SOURCES)
    assert result.ungrounded == ["The Pro plan includes a dedicated account manager."]


def test_suppress_policy_removes_unsupported_sentences():
    response = "Annual billing gives a 20% discount. Enterprise has unlimited seats."
    result = verify(response, SOURCES, policy="suppress")
    assert result.text == "Annual billing gives a 20% discount. [2]"


def test_regenerate_rewrites_once_then_suppresses():
    llm = ScriptedLLM(["The Pro plan costs $49 per month. It also has free onboarding."])
    result = verify("The Pro plan costs $99.", SOURCES, policy="regenerate", llm=llm)
    assert len(llm.calls) == 1
    assert result.text == "The Pro plan costs $49 per month. [1]"


def test_questions_and_advice_are_not_treated_as_claims():
    assert extract_claims("Would you like a quote? You can upgrade any time. Seats cost extra.") == [
        "Seats cost extra."
    ]
