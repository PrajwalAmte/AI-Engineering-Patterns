from common.fakes import ScriptedLLM
from cost_and_efficiency.cascading_context_assembly import INSUFFICIENT, Tier, answer

DOCS = [
    "Refunds are issued within 5 business days.",
    "Shipping to Canada takes 7 days.",
    "Enterprise plans include SSO via SAML.",
    "Data is stored in eu-west-1 for EU customers.",
]


def retrieve(query, k):
    return DOCS[:k]


def reader(prompt):
    """Answers only if a doc containing the keyword is in the context."""
    context = prompt.split("Context:")[1].split("Question:")[0]
    question = prompt.split("Question:")[1].lower()
    for keyword in ("refund", "canada", "sso", "eu-west"):
        if keyword in question:
            return f"answer about {keyword}" if keyword in context.lower() else INSUFFICIENT
    return INSUFFICIENT


def tiers():
    return [Tier(1, ScriptedLLM(reader)), Tier(2, ScriptedLLM(reader)), Tier(4, ScriptedLLM(reader))]


def test_easy_question_stops_at_the_first_tier():
    t = tiers()
    result = answer("How long do refunds take?", retrieve, t)
    assert (result.tier, result.chunks_used, result.calls) == (0, 1, 1)
    assert t[1].llm.calls == []


def test_harder_question_escalates_only_as_far_as_needed():
    result = answer("Do you support SSO?", retrieve, tiers())
    assert (result.answer, result.tier, result.chunks_used) == ("answer about sso", 2, 4)


def test_unanswerable_question_returns_an_honest_miss():
    result = answer("What is the CEO's favourite colour?", retrieve, tiers())
    assert "couldn't find" in result.answer
    assert result.calls == 3


def test_prompt_tells_the_model_how_to_say_it_cannot_answer():
    t = tiers()
    answer("refunds?", retrieve, t)
    assert f"reply with exactly {INSUFFICIENT}" in t[0].llm.calls[0]
