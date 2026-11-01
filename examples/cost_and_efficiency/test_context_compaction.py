from common.fakes import ScriptedLLM
from cost_and_efficiency.context_compaction import Compactor, Message


def count(text):
    return len(text.split())


def words(n, tag="w"):
    return " ".join([tag] * n)


def make(**kw):
    llm = ScriptedLLM(["GOAL: fix the bug\nDONE: read files\nDECISIONS: none\nOPEN: write patch"])
    defaults = dict(summarize=llm, count=count, window=200, trigger=0.8, target=0.5, keep_recent=2)
    defaults.update(kw)
    return Compactor(**defaults), llm


def transcript(tool_size=40, turns=4):
    msgs = [Message("user", "Fix the failing test in billing.py")]
    for i in range(turns):
        msgs.append(Message("assistant", f"step {i}: reading file"))
        msgs.append(Message("tool", words(tool_size, f"line{i}"), name="read_file"))
    return msgs


def test_small_contexts_are_left_alone():
    compactor, llm = make()
    msgs = transcript(tool_size=5)
    assert compactor.maybe_compact(msgs) is msgs
    assert llm.calls == []


def test_clearing_old_tool_results_is_tried_before_summarising():
    compactor, llm = make()
    out = compactor.maybe_compact(transcript())
    assert llm.calls == []
    assert out[2].content.startswith("[cleared read_file result, 40 tokens]")
    assert out[-1].content.startswith("line3")  # recent tool result untouched
    assert compactor.log == ["cleared tool results"]


def test_summarises_when_clearing_is_not_enough():
    compactor, llm = make()
    msgs = transcript(tool_size=10, turns=3)
    msgs += [Message("assistant", words(150, "reasoning")), Message("user", "continue"), Message("assistant", "ok")]
    out = compactor.maybe_compact(msgs)
    assert len(llm.calls) == 1
    assert out[0].content == "Fix the failing test in billing.py"
    assert out[1].content.startswith("[Summary of earlier work]\nGOAL:")
    assert [m.content for m in out[-2:]] == ["continue", "ok"]


def test_task_message_survives_any_compaction():
    compactor, _ = make()
    msgs = transcript(tool_size=60, turns=5)
    assert compactor.maybe_compact(msgs)[0].content == msgs[0].content
