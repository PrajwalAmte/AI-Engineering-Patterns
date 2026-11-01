from common.fakes import ScriptedLLM
from retrieval_and_memory.sliding_context_window import ConversationMemory


def words(n, tag):
    return " ".join(f"{tag}{i}" for i in range(n))


def make(summary="- summary", **kw):
    llm = ScriptedLLM([summary])
    defaults = dict(count_tokens=lambda s: len(s.split()), verbatim_budget=50, archive_budget=20, consolidate_batch=2)
    defaults.update(kw)
    return ConversationMemory(summarize=llm, **defaults), llm


def test_short_conversations_stay_verbatim():
    memory, llm = make()
    memory.add("user", "hi")
    memory.add("assistant", "hello")
    assert llm.calls == []
    assert "user: hi" in memory.context("SYSTEM")


def test_oldest_turns_are_consolidated_when_over_budget():
    memory, llm = make()
    for i in range(4):
        memory.add("user", words(20, f"t{i}_"))
    assert len(llm.calls) >= 1
    assert "t0_0" in llm.calls[0]
    assert memory.verbatim[-1].text.startswith("t3_")
    assert "Earlier in this conversation" in memory.context("SYSTEM")


def test_pinned_facts_survive_any_compression():
    memory, _ = make(summary="- user discussed food")
    memory.add("user", "Remember that I'm allergic to peanuts.")
    for i in range(10):
        memory.add("assistant", words(20, f"a{i}_"))
    context = memory.context("SYSTEM")
    assert "allergic to peanuts" in context
    assert all("peanuts" not in t.text for t in memory.verbatim)


def test_archive_is_reconsolidated_when_it_outgrows_its_budget():
    memory, llm = make(summary=words(12, "s"))  # each summary is 12 tokens; archive budget is 20
    for i in range(12):
        memory.add("user", words(20, f"t{i}_"))
    assert len(memory.archive) == 1
    assert any(call.count("s0") >= 2 for call in llm.calls)  # a summary of summaries happened


def test_most_recent_exchange_is_never_summarised():
    memory, _ = make()
    memory.add("user", words(200, "huge"))
    memory.add("assistant", words(200, "reply"))
    assert len(memory.verbatim) == 2
