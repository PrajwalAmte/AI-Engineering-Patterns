---
title: Semantic Rollback
pillar: loop-engineering
status: emerging
tags: [agents, rollback, state-management, recovery, agentic]
related:
  - Loop Termination
  - No-Progress Detection
  - Circuit Breaker for LLMs
  - Maker-Verifier Split
contributors: ["@PrajwalAmte"]
last_updated: "2026-07"
description: Checkpoint agentic workflow state at semantically coherent milestones and restore to the last valid checkpoint when partial failure corrupts downstream steps.
sidebar:
  order: 5
---

## What It Is

Semantic Rollback checkpoints the state of a multi-step agentic workflow at points where the agent has reached a semantically coherent intermediate result—a valid plan, a complete sub-task, a verified data fetch. When a later step fails or produces corrupted output, the system rolls back to the last valid checkpoint and retries from there, rather than restarting from scratch or continuing with corrupted state. Unlike database transactions, rollback targets semantic coherence, not just data consistency.

## The Problem It Solves

Multi-step LLM agents fail in the middle of complex tasks, leaving partial work in an inconsistent state:

- Agent writes 3 of 5 required sections of a document, then halts on step 4 due to a tool timeout. Restarting from scratch discards 3 valid sections.
- Agent executes a 10-step research pipeline. Step 7 retrieves incorrect data due to a hallucinated query. Steps 8-10 build on corrupted data and produce nonsensical conclusions.
- Agent calls an external API at step 3, receives ambiguous output, and produces a plan that looks valid but is semantically incompatible with the original goal. The error compounds silently through remaining steps.

Existing patterns handle adjacent but different problems: Loop Termination stops infinite loops, No-Progress Detection halts stalled agents, Circuit Breaker handles provider failures. None of them restore the agent to a known-good intermediate state and resume from there. Without Semantic Rollback, failure means either starting over (wasting all prior work) or continuing with corrupted state (producing garbage outputs).

## How It Works

<pre class="mermaid">
flowchart TD
    A[Agent starts task] --> B[Execute step]
    B --> C[Checkpoint validator]
    C -->|Semantically valid| D[Save checkpoint]
    C -->|Invalid or corrupted| E{Previous checkpoint available?}
    D --> F[Execute next step]
    F --> C
    E -->|Yes| G[Rollback to last checkpoint]
    E -->|No| H[Abort: no valid state to restore]
    G --> I[Increment retry counter for this step]
    I --> J{Retry limit reached?}
    J -->|No| B
    J -->|Yes| K[Escalate or skip step with degraded output]
    H --> L[Report failure with partial results]
</pre>

1. **Define checkpoint boundaries**: Identify semantically coherent milestones in the workflow (e.g., "research complete," "plan validated," "section drafted"). These are points where intermediate output is independently verifiable.
2. **Checkpoint validation**: Before saving a checkpoint, validate that the current state is semantically coherent:
   - Structural validation (required fields present, format correct)
   - Semantic validation (output is consistent with task goal and prior checkpoints)
   - Optional: LLM-based validation ("Is this a complete and valid plan for the original task?")
3. **Checkpoint storage**: Save the full agent state at each validated milestone: context, intermediate outputs, tool call results, step index.
4. **Failure detection**: Detect failures via exception from tool call, validation failure on step output, No-Progress Detection signal, or LLM quality signal.
5. **Rollback execution**: Restore the most recent valid checkpoint. Invalidate all state produced after that checkpoint.
6. **Retry with modification**: Retry the failed step, optionally with a different strategy, different tool, or reduced scope.
7. **Retry cap**: Limit retries per checkpoint to prevent infinite rollback loops. After N retries, escalate or skip with a degraded output.

## When to Use It

- Multi-step agentic workflows where steps have semantic dependencies (output of step N is input to step N+1)
- Tasks where restarting from scratch has high cost (long-running workflows, expensive tool calls, user-facing latency)
- Workflows with identifiable intermediate milestones that can be independently validated
- Systems that make external API calls or file writes mid-workflow where partial state must be managed
- Agents expected to handle occasional tool failures or hallucinated intermediate outputs gracefully

## When NOT to Use It

- Single-step LLM calls (no intermediate state to checkpoint)
- Workflows where all steps are cheap and fast enough that restarting is acceptable
- Workflows with no identifiable semantic milestones (continuous stream of tool calls without coherent intermediate states)
- Stateless workflows where each step is independent and does not consume prior step output
- Systems where checkpoint storage overhead outweighs the recovery benefit

## Trade-offs

1. **Checkpoint overhead** — Every validated checkpoint incurs a storage write and validation cost. LLM-based validators add 200-500ms per checkpoint. For short workflows (fewer than 5 steps), overhead may exceed the benefit.

2. **Rollback does not fix root cause** — Rolling back and retrying the same step with the same inputs often reproduces the same failure. Rollback is most useful when combined with a strategy change (different prompt, different tool, different data source) on retry.

3. **Checkpoint validity is only as good as your validator** — A validator that passes corrupted state creates false confidence. Steps downstream of a bad checkpoint continue accumulating errors. Invest in validator quality, not just checkpoint frequency.

4. **Semantic coherence is subjective** — "Is this plan valid?" is not a binary question. Validators may disagree across runs, making rollback behavior non-deterministic. Use structural validators (schema, required fields) as primary gate and LLM validators as secondary signal.

## Failure Modes

### Rollback Loop
**Trigger**: Step N fails, rolls back to checkpoint N-1, retries step N, fails again for the same reason.
**Symptom**: Agent spins on the same step consuming cost and time. User sees high latency and eventual failure.
**Mitigation**: Increment retry counter per checkpoint. On first retry, modify strategy (different prompt). On second retry, change tool or data source. On third, degrade gracefully (skip step, continue with partial output). Never retry identically.

### Silent Validator Pass on Corrupted State
**Trigger**: Step 3 produces a valid-looking plan that is subtly semantically wrong (addresses a different goal, uses incorrect constraints). Structural validator passes. State is checkpointed.
**Symptom**: All subsequent steps run successfully but build on a corrupted foundation. Final output is coherent but wrong.
**Mitigation**: Add cross-checkpoint consistency validation: before advancing past each checkpoint, verify it is consistent with the original task goal and all prior checkpoints.

### Checkpoint State Explosion
**Trigger**: Long workflow (20+ steps) with large intermediate state (multi-page documents, large data fetches). Every checkpoint stores the full state.
**Symptom**: Storage grows proportionally to workflow length times state size. For concurrent users, storage cost becomes prohibitive.
**Mitigation**: Store only the delta from the prior checkpoint rather than full state. Use content-addressable storage with deduplication. Set maximum checkpoint history (e.g., keep last 3 only).

## Implementation Example

```python
import json
import copy
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Callable
from enum import Enum

class CheckpointStatus(Enum):
    VALID = "valid"
    INVALID = "invalid"

@dataclass
class Checkpoint:
    step_index: int
    step_name: str
    state: dict[str, Any]
    status: CheckpointStatus = CheckpointStatus.VALID
    retry_count: int = 0

@dataclass
class AgentState:
    task: str
    current_step: int = 0
    outputs: dict[str, Any] = field(default_factory=dict)
    context: list[dict] = field(default_factory=list)

class SemanticRollbackAgent:
    """
    Wraps an agentic workflow with checkpoint-and-rollback capability.
    """

    def __init__(
        self,
        max_retries_per_step: int = 3,
        validator: Optional[Callable[[AgentState, str], bool]] = None
    ):
        self.max_retries_per_step = max_retries_per_step
        self.validator = validator or self._default_validator
        self.checkpoints: list[Checkpoint] = []

    def _default_validator(self, state: AgentState, step_name: str) -> bool:
        """Structural validator: check required outputs exist and are non-empty"""
        output = state.outputs.get(step_name)
        if output is None:
            return False
        if isinstance(output, str) and len(output.strip()) < 10:
            return False
        if isinstance(output, dict) and not output:
            return False
        return True

    def _save_checkpoint(self, state: AgentState, step_name: str) -> None:
        checkpoint = Checkpoint(
            step_index=state.current_step,
            step_name=step_name,
            state=copy.deepcopy(asdict(state))
        )
        self.checkpoints.append(checkpoint)
        print(f"[checkpoint] Saved at step '{step_name}' (index {state.current_step})")

    def _rollback(self, state: AgentState) -> Optional[AgentState]:
        if not self.checkpoints:
            return None
        last = self.checkpoints[-1]
        last.retry_count += 1
        print(f"[rollback] Restoring to '{last.step_name}' (retry {last.retry_count}/{self.max_retries_per_step})")
        return AgentState(**last.state)

    async def run_step(
        self,
        state: AgentState,
        step_name: str,
        step_fn: Callable[[AgentState], Any],
        retry_strategy: Optional[Callable[[int, AgentState], AgentState]] = None
    ) -> tuple[AgentState, bool]:
        """Execute one step with checkpoint and rollback support."""
        try:
            result = await step_fn(state)
            state.outputs[step_name] = result
            state.current_step += 1

            if self.validator(state, step_name):
                self._save_checkpoint(state, step_name)
                return state, True
            else:
                raise ValueError(f"Validation failed for step '{step_name}'")

        except Exception as e:
            print(f"[step-fail] Step '{step_name}' failed: {e}")
            restored_state = self._rollback(state)
            if restored_state is None:
                print("[rollback-fail] No checkpoint available; cannot recover")
                return state, False

            last_checkpoint = self.checkpoints[-1]
            if last_checkpoint.retry_count >= self.max_retries_per_step:
                print(f"[retry-limit] Max retries reached for '{last_checkpoint.step_name}'")
                restored_state.outputs[step_name] = None
                restored_state.current_step += 1
                return restored_state, False

            if retry_strategy:
                restored_state = retry_strategy(last_checkpoint.retry_count, restored_state)

            return restored_state, False


# Usage example
async def run_research_agent(task: str, llm_call: Callable):
    """4-step research agent with semantic rollback"""
    agent = SemanticRollbackAgent(max_retries_per_step=2)
    state = AgentState(task=task)

    state, _ = await agent.run_step(
        state=state,
        step_name="research_plan",
        step_fn=lambda s: llm_call(f"Create a research plan for: {s.task}")
    )

    state, _ = await agent.run_step(
        state=state,
        step_name="fetch_sources",
        step_fn=lambda s: fetch_sources(s.outputs.get("research_plan")),
        retry_strategy=lambda attempt, s: s  # extend with modified prompt on retry
    )

    state, _ = await agent.run_step(
        state=state,
        step_name="synthesis",
        step_fn=lambda s: llm_call(
            f"Synthesize findings:\n{json.dumps(s.outputs.get('fetch_sources', {}))}"
        )
    )

    return state.outputs
```

## Tool Landscape

| Tool | Type | Notes |
|------|------|-------|
| LangGraph | Open-source | Native support for checkpointing and state persistence in graph-based agents |
| CrewAI | Open-source | Task-level retry with some checkpoint support |
| Temporal | Workflow engine | Production-grade workflow state management with replay; can wrap LLM steps |
| Apache Airflow | Orchestration | Task-level retry with state persistence; not LLM-native but adaptable |
| Custom implementation | DIY | Required for semantic validation logic tailored to specific agent workflows |

## Related Patterns

- **[Loop Termination](loop-termination.md)** — Loop Termination stops runaway agents; Semantic Rollback recovers them. Use both: terminate if retries are exhausted after rollback.
- **[No-Progress Detection](no-progress-detection.md)** — No-Progress Detection signals that the agent is stuck; Semantic Rollback is the recovery mechanism to act on that signal.
- **[Maker-Verifier Split](maker-verifier-split.md)** — Verifier output serves as the checkpoint validator in Semantic Rollback; only accept checkpoints that pass the verifier quality gate.
- **[Circuit Breaker for LLMs](../reliability/circuit-breaker.md)** — Circuit Breaker handles provider-level failures; Semantic Rollback handles workflow-level semantic failures. Both can coexist in the same system.

## Further Reading

- [LangGraph: Stateful, Multi-Actor Applications](https://langchain-ai.github.io/langgraph/) — Production framework with native checkpoint and rollback support
- [Temporal Workflow Durability](https://docs.temporal.io/workflows) — Battle-tested approach to durable, recoverable workflow execution
- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) — Foundation for multi-step agentic workflows that semantic rollback protects
- [Voyager: An Open-Ended Embodied Agent with Large Language Models](https://arxiv.org/abs/2305.16291) — Production example of checkpointed skill acquisition in LLM agents
