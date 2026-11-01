"""Multi-Agent Orchestration (orchestrator-worker, manager-as-tool).

The orchestrator plans, fans subtasks out to workers that each get a fresh,
narrow context, and synthesises their condensed results. The two things that
keep this from going wrong are explicit subtask boundaries and hard limits on
agents, rounds and how much each worker may send back.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

LLM = Callable[[str], str]

PLAN_PROMPT = """You are coordinating research on: {task}
Findings so far:
{findings}

Reply with JSON: {{"done": bool, "subtasks": [{{"objective": str, "exclude": str}}]}}.
Use at most {max_agents} subtasks. Each objective must not overlap the others.
Set done=true when the findings answer the task."""

WORKER_PROMPT = """Objective: {objective}
Out of scope (another agent covers it): {exclude}
Return only your key findings, at most {max_words} words."""


@dataclass
class Subtask:
    objective: str
    exclude: str = ""


@dataclass
class Orchestrator:
    planner: LLM  # the strong model: plans and synthesises
    worker: LLM  # often a cheaper model; runs with a fresh context per subtask
    max_agents: int = 4
    max_rounds: int = 3
    max_words_per_worker: int = 150
    trace: list[dict] = field(default_factory=list)

    def run(self, task: str) -> str:
        findings: dict[str, str] = {}
        for round_no in range(1, self.max_rounds + 1):
            plan = self._plan(task, findings)
            new = [s for s in plan["subtasks"] if s.objective not in findings][: self.max_agents]
            self.trace.append({"round": round_no, "done": plan["done"], "spawned": [s.objective for s in new]})
            if plan["done"] or not new:
                break
            with ThreadPoolExecutor(max_workers=len(new)) as pool:
                results = pool.map(self._delegate, new)
            for subtask, result in zip(new, results):
                findings[subtask.objective] = result

        notes = "\n".join(f"- {k}: {v}" for k, v in findings.items())
        return self.planner(f"Write the final answer to: {task}\nUsing these findings:\n{notes}")

    def _plan(self, task: str, findings: dict[str, str]) -> dict:
        raw = self.planner(
            PLAN_PROMPT.format(
                task=task,
                findings="\n".join(f"- {k}: {v}" for k, v in findings.items()) or "(none yet)",
                max_agents=self.max_agents,
            )
        )
        try:
            data = json.loads(raw)
            subtasks = [Subtask(s["objective"], s.get("exclude", "")) for s in data.get("subtasks", [])]
            return {"done": bool(data.get("done")), "subtasks": subtasks}
        except (json.JSONDecodeError, KeyError, TypeError):
            # A malformed plan ends the loop rather than spawning garbage work.
            return {"done": True, "subtasks": []}

    def _delegate(self, subtask: Subtask) -> str:
        reply = self.worker(
            WORKER_PROMPT.format(
                objective=subtask.objective, exclude=subtask.exclude or "nothing", max_words=self.max_words_per_worker
            )
        )
        # Enforce the budget even if the worker ignores the instruction:
        # the orchestrator's context is the scarce resource.
        return " ".join(reply.split()[: self.max_words_per_worker])
