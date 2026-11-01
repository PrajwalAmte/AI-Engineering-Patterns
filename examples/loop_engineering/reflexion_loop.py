"""Reflexion Loop.

Three roles, three calls: the actor attempts, the evaluator checks (ideally a
test, not an opinion), and on failure a reflection step writes one short,
specific lesson into memory. The next attempt reads the lessons. Memory is
small and de-duplicated: a lesson repeated is a sign the loop is stuck.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

Actor = Callable[[str, list[str]], str]  # (task, lessons) -> attempt
Evaluator = Callable[[str], tuple[bool, str]]  # attempt -> (passed, feedback)
Reflector = Callable[[str, str, str], str]  # (task, attempt, feedback) -> one-sentence lesson


@dataclass
class Memory:
    max_lessons: int = 5
    lessons: list[str] = field(default_factory=list)

    def add(self, lesson: str) -> bool:
        """Returns False if this lesson was already learned (a stall signal)."""
        key = lesson.strip().lower()
        if any(key == old.strip().lower() for old in self.lessons):
            return False
        self.lessons.append(lesson.strip())
        self.lessons = self.lessons[-self.max_lessons :]  # recent lessons matter most
        return True


@dataclass
class Result:
    passed: bool
    attempt: str
    trials: int
    lessons: list[str]
    stop_reason: str


def reflexion(
    task: str, actor: Actor, evaluate: Evaluator, reflect: Reflector, max_trials: int = 4, memory: Memory | None = None
) -> Result:
    memory = memory or Memory()
    attempt = ""
    for trial in range(1, max_trials + 1):
        attempt = actor(task, list(memory.lessons))
        passed, feedback = evaluate(attempt)
        if passed:
            return Result(True, attempt, trial, memory.lessons, "passed")
        lesson = reflect(task, attempt, feedback)
        if not memory.add(lesson):
            return Result(False, attempt, trial, memory.lessons, "repeated lesson: not learning")
    return Result(False, attempt, max_trials, memory.lessons, "out of trials")


REFLECT_PROMPT = """Task: {task}
Your attempt: {attempt}
What went wrong: {feedback}
In ONE sentence, state the specific mistake and what to do differently next time.
Don't restate the task. Don't apologise."""
