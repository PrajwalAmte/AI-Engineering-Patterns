import json

from common.fakes import ScriptedLLM
from inference_and_serving.multi_agent_orchestration import Orchestrator


def plan(*objectives, done=False):
    return json.dumps({"done": done, "subtasks": [{"objective": o, "exclude": "pricing"} for o in objectives]})


def planner_script(plans):
    plans = list(plans)

    def respond(prompt):
        if prompt.startswith("Write the final answer"):
            return "FINAL:" + prompt.split("findings:\n", 1)[1]
        return plans.pop(0) if plans else plan(done=True)

    return ScriptedLLM(respond)


def test_fans_out_and_synthesises_condensed_findings():
    planner = planner_script([plan("vendor A features", "vendor B features")])
    worker = ScriptedLLM(lambda p: "finding for " + p.split("\n")[0].removeprefix("Objective: "))
    result = Orchestrator(planner, worker).run("compare vendors")
    assert "vendor A features: finding for vendor A features" in result
    assert "vendor B features: finding for vendor B features" in result
    assert all("Out of scope" in c for c in worker.calls)


def test_caps_agents_per_round_and_rounds_overall():
    planner = planner_script([plan(*[f"topic {i}" for i in range(10)])] + [plan(f"more {i}") for i in range(10)])
    worker = ScriptedLLM(["ok"])
    orch = Orchestrator(planner, worker, max_agents=3, max_rounds=2)
    orch.run("big task")
    assert len(worker.calls) == 3 + 1
    assert len(orch.trace) == 2


def test_does_not_respawn_work_already_done():
    planner = planner_script([plan("topic"), plan("topic")])
    worker = ScriptedLLM(["ok"])
    Orchestrator(planner, worker).run("task")
    assert len(worker.calls) == 1


def test_worker_output_is_truncated_to_budget():
    planner = planner_script([plan("topic")])
    worker = ScriptedLLM(["word " * 1000])
    result = Orchestrator(planner, worker, max_words_per_worker=5).run("task")
    assert result.count("word") == 5


def test_malformed_plan_stops_instead_of_spawning():
    planner = planner_script(["not json"])
    worker = ScriptedLLM(["ok"])
    Orchestrator(planner, worker).run("task")
    assert worker.calls == []
