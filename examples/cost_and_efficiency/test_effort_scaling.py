import pytest

from cost_and_efficiency.effort_scaling import BudgetExhausted, Run, classify


def test_classifies_by_shape_of_the_task():
    assert classify("What is our PTO policy?").tier == "lookup"
    assert classify("Compare Postgres vs DynamoDB for our event store").tier == "analysis"
    assert classify("Research the vector database landscape for us").tier == "research"


def test_many_named_entities_imply_breadth():
    assert classify("Pinecone Weaviate Qdrant Milvus Chroma pricing").tier == "research"


def test_tool_budget_is_enforced_not_just_suggested():
    run = Run(classify("What is our PTO policy?"))
    for _ in range(3):
        run.tool(lambda q: "result", "pto")
    with pytest.raises(BudgetExhausted):
        run.tool(lambda q: "result", "pto")


def test_lookups_cannot_spawn_subagents():
    with pytest.raises(BudgetExhausted):
        Run(classify("When is payday?")).spawn()


def test_record_shows_whether_the_tier_was_right():
    run = Run(classify("Compare A vs B"))
    run.tool(lambda: "x")
    run.stopped_early = True
    row = run.record()
    assert row == {
        "tier": "analysis",
        "tool_calls": 1,
        "tool_budget": 15,
        "subagents": 0,
        "hit_ceiling": False,
        "stopped_early": True,
    }
