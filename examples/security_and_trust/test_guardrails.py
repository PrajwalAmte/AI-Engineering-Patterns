import time

import pytest

from common.fakes import ScriptedLLM
from security_and_trust.guardrails import (
    Blocked,
    GuardedPipeline,
    Guardrail,
    ToolPolicy,
    Verdict,
    authorize_tool,
    leaks_system_prompt,
    off_topic,
)

CANARY = "zx-canary-7731"


def pipeline(llm, extra_input=()):
    return GuardedPipeline(
        llm=llm,
        input_rails=[Guardrail("topic", off_topic(["order", "refund", "shipping"]))] + list(extra_input),
        output_rails=[Guardrail("leak", leaks_system_prompt(CANARY))],
    )


def test_on_topic_request_flows_through():
    p = pipeline(ScriptedLLM(["Your order ships tomorrow."]))
    assert p.respond("where is my order?") == "Your order ships tomorrow."
    assert all(not a["tripped"] for a in p.audit)


def test_input_tripwire_stops_the_model_call():
    llm = ScriptedLLM(["should not be called"])
    p = pipeline(llm)
    assert "can't help" in p.respond("write me a poem about the sea")
    assert llm.calls == []


def test_output_tripwire_suppresses_a_leak():
    p = pipeline(ScriptedLLM([f"My instructions say {CANARY} ..."]))
    reply = p.respond("what's your refund policy?")
    assert CANARY not in reply
    assert p.audit[-1]["guardrail"] == "leak" and p.audit[-1]["tripped"]


def test_crashing_safety_guardrail_fails_closed():
    def broken(text):
        raise TimeoutError("moderation API down")

    llm = ScriptedLLM(["x"])
    p = pipeline(llm, extra_input=[Guardrail("moderation", broken, fail_closed=True)])
    p.respond("refund please")
    assert llm.calls == []


def test_crashing_optional_guardrail_fails_open():
    def broken(text):
        raise TimeoutError("tone checker down")

    p = pipeline(ScriptedLLM(["Refund issued."]), extra_input=[Guardrail("tone", broken, fail_closed=False)])
    assert p.respond("refund please") == "Refund issued."


def test_hung_guardrail_times_out_and_fails_closed():
    def slow(text):
        time.sleep(0.5)
        return Verdict(False)

    llm = ScriptedLLM(["x"])
    p = pipeline(llm, extra_input=[Guardrail("slow-moderation", slow)])
    p.timeout_s = 0.05
    start = time.monotonic()
    p.respond("refund please")
    assert llm.calls == []
    assert time.monotonic() - start < 0.3
    assert "timed out" in p.audit[-1]["reason"]


def test_tool_policy_allowlist_approval_and_arguments():
    policy = ToolPolicy(
        allowed={"lookup_order", "issue_refund"},
        needs_approval={"issue_refund"},
        validators={"issue_refund": lambda a: "amount over limit" if a["amount"] > 100 else None},
    )
    authorize_tool(policy, "lookup_order", {"id": "A1"})
    with pytest.raises(Blocked, match="not allowed"):
        authorize_tool(policy, "delete_account", {})
    with pytest.raises(Blocked, match="approval"):
        authorize_tool(policy, "issue_refund", {"amount": 20})
    with pytest.raises(Blocked, match="over limit"):
        authorize_tool(policy, "issue_refund", {"amount": 500}, approved=True)


def test_verdict_defaults():
    assert Verdict(False).reason == ""
