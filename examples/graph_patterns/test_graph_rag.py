from common.fakes import ScriptedLLM
from graph_patterns.graph_rag import KnowledgeGraph, Triple, answer, build_context

KG = KnowledgeGraph(
    [
        Triple("checkout-service", "depends on", "payments-db", "arch.md"),
        Triple("refund-worker", "depends on", "payments-db", "arch.md"),
        Triple("checkout-service", "owned by", "Team Orion", "owners.yaml"),
        Triple("refund-worker", "owned by", "Team Vega", "owners.yaml"),
        Triple("search-service", "owned by", "Team Lyra", "owners.yaml"),
    ],
    aliases={"payments database": "payments-db"},
)


def test_finds_entities_including_aliases():
    assert KG.entities_in("Who is affected if the payments database goes down?") == ["payments-db"]


def test_two_hops_reach_the_owning_teams():
    facts = {(t.subject, t.relation, t.object) for t in KG.neighbourhood(["payments-db"], hops=2)}
    assert ("checkout-service", "owned by", "Team Orion") in facts
    assert ("refund-worker", "owned by", "Team Vega") in facts
    assert not any("Lyra" in f[2] for f in facts)  # unrelated service stays out


def test_one_hop_is_not_enough_for_the_ownership_question():
    facts = {t.object for t in KG.neighbourhood(["payments-db"], hops=1)}
    assert "Team Orion" not in facts


def test_context_carries_sources_for_citation():
    context = build_context("what breaks if payments-db is down", KG, passages=[])
    assert "- checkout-service depends on payments-db [arch.md]" in context
    assert "- checkout-service owned by Team Orion [owners.yaml]" in context


def test_fact_cap_bounds_the_prompt():
    big = KnowledgeGraph([Triple("hub", "links", f"n{i}") for i in range(500)])
    assert len(big.neighbourhood(["hub"], max_facts=30)) == 30


def test_answer_passes_graph_context_to_the_model():
    llm = ScriptedLLM(["Teams Orion and Vega."])
    answer("Which teams are hit if payments-db fails?", KG, llm)
    assert "Team Vega" in llm.calls[0]
