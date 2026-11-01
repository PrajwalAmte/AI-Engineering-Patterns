from common.fakes import ScriptedLLM
from retrieval_and_memory.retrieval_quality_gate import answer, gate

CHUNKS = [
    "Python's memory model uses reference counting plus a cyclic garbage collector.",
    "The python is a large non-venomous snake found in Africa and Asia.",
    "Our Python style guide requires type hints on public functions.",
]


def test_keeps_the_relevant_chunk_and_drops_lookalikes():
    result = gate("python memory model garbage collector", CHUNKS)
    assert [c for c, _ in result.kept] == [CHUNKS[0]]
    assert len(result.dropped) == 2


def test_abstains_when_nothing_is_relevant():
    assert gate("what is the parental leave policy", CHUNKS).decision == "abstain"


def test_abstention_never_reaches_the_model():
    llm = ScriptedLLM(["made-up answer"])
    reply = answer("what is the parental leave policy", CHUNKS, llm)
    assert "couldn't find" in reply
    assert llm.calls == []


def test_only_kept_chunks_go_into_the_prompt():
    llm = ScriptedLLM(["ok"])
    answer("python memory model garbage collector", CHUNKS, llm)
    assert "reference counting" in llm.calls[0]
    assert "snake" not in llm.calls[0]


def test_relative_cutoff_drops_chunks_far_below_the_best_one():
    scores = {"a": 0.95, "b": 0.55, "c": 0.9}
    result = gate("q", ["a", "b", "c"], score=lambda q, c: scores[c], threshold=0.5)
    assert [c for c, _ in result.kept] == ["a", "c"]
