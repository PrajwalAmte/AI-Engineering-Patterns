from common.fakes import FakeClock
from governance.human_in_the_loop import Action, Decision, Gate, default_classifier


def executor(log):
    def execute(tool, args):
        log.append((tool, args))
        return f"{tool} ok"

    return execute


def gate(answer, clock=None):
    clock = clock or FakeClock()

    def ask(action):
        clock.advance(10)
        return answer(action) if callable(answer) else answer

    return Gate(classify=default_classifier, ask=ask, timeout_s=60, clock=clock)


def test_read_only_actions_run_without_asking():
    asked, log = [], []
    g = gate(lambda a: asked.append(a) or Decision(True))
    assert g.run(Action("search_orders", {"q": "late"}, "find late orders"), executor(log)) == "search_orders ok"
    assert asked == []


def test_consequential_action_waits_for_approval():
    log = []
    g = gate(Decision(True, by="dana"))
    g.run(Action("send_email", {"to": "c@x.com"}, "notify customer"), executor(log))
    assert log == [("send_email", {"to": "c@x.com"})]
    assert g.audit[-1]["outcome"] == "approved by dana"


def test_approver_can_edit_arguments():
    log = []
    g = gate(Decision(True, args={"amount": 50}, by="dana"))
    g.run(Action("issue_refund", {"amount": 500}, "customer upset"), executor(log))
    assert log == [("issue_refund", {"amount": 50})]


def test_denial_is_returned_to_the_agent_not_executed():
    log = []
    g = gate(Decision(False, by="dana", note="wrong customer"))
    result = g.run(Action("send_email", {"to": "c@x.com"}, "notify"), executor(log))
    assert result.startswith("ACTION NOT TAKEN") and "wrong customer" in result
    assert log == []


def test_silence_means_no():
    log = []
    g = gate(None)
    result = g.run(Action("send_email", {"to": "c@x.com"}, "notify"), executor(log))
    assert "timeout" in result and log == []


def test_forbidden_actions_are_never_executed_even_if_approved():
    log = []
    g = gate(Decision(True))
    g.run(Action("delete_account", {"id": 1}, "cleanup"), executor(log))
    assert log == []


def test_session_grant_skips_repeat_approvals():
    asked, log = [], []
    g = gate(lambda a: asked.append(a) or Decision(True, by="dana"))
    g.grant_for_session("write_file")
    for i in range(3):
        g.run(Action("write_file", {"path": f"f{i}"}, "edit"), executor(log))
    assert asked == [] and len(log) == 3
