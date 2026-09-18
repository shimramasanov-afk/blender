"""One Task at a time. Skills go through LiveRuntime. No planner."""

from __future__ import annotations

from l2_brain.live.runtime import LiveRuntime
from l2_brain.live.tasks.base import Task
from l2_brain.live.tasks.result import TaskResult, TaskStatus
from l2_brain.live.world_state import AgentMode


class TaskRunner:
    def __init__(self, runtime: LiveRuntime) -> None:
        self.runtime = runtime
        self.task: Task | None = None
        self.last_result: TaskResult | None = None
        self.transitions: list[dict[str, object]] = []

    def start(self, task: Task) -> TaskResult:
        if self.task is not None and self.last_result is not None and not self.last_result.terminal:
            return TaskResult(TaskStatus.FAILED, reason="task_busy", data={"active": self.task.name})
        self.task = task
        state = self.runtime.observe()
        result = task.start(self.runtime, state)
        self.last_result = result
        self._log("start", result)
        return result

    def tick(self) -> TaskResult:
        if self.task is None:
            return TaskResult(TaskStatus.FAILED, reason="no_active_task")
        if self.last_result is not None and self.last_result.terminal:
            return self.last_result
        if self.runtime.active_skill is not None:
            skill = self.runtime.tick()
            if skill is not None:
                self.transitions.append(
                    {
                        "kind": "skill_tick",
                        "skill": None if self.runtime.active_skill is None else self.runtime.active_skill.name,
                        "status": skill.status.value,
                        "reason": skill.reason,
                    }
                )
        result = self.task.tick(self.runtime, self.runtime.state)
        self.last_result = result
        self._log("tick", result)
        if result.terminal and self.runtime.mode is not AgentMode.ABORTED:
            if self.runtime.active_skill is None:
                self.runtime.mode = AgentMode.IDLE
        return result

    def cancel(self, reason: str = "operator_cancel") -> TaskResult:
        if self.task is None:
            if self.runtime.active_skill is not None:
                self.runtime.cancel_skill(reason)
            return TaskResult(TaskStatus.ABORTED, reason=reason)
        result = self.task.cancel(self.runtime, reason)
        self.last_result = result
        self._log("cancel", result)
        return result

    def run_until_done(self, *, max_ticks: int, sleeper) -> TaskResult:
        if self.last_result is None:
            return TaskResult(TaskStatus.FAILED, reason="not_started")
        ticks = 0
        while not self.last_result.terminal and ticks < max_ticks:
            sleeper(self.runtime._tick_s)
            self.tick()
            ticks += 1
        if not self.last_result.terminal:
            return self.cancel("task_timeout")
        return self.last_result

    def summary(self) -> dict[str, object]:
        task = self.task
        last = self.last_result
        return {
            "task": None if task is None else task.name,
            "status": None if last is None else last.status.value,
            "reason": None if last is None else last.reason,
            "trace": list(getattr(task, "trace", [])),
            "transitions": list(self.transitions),
            "runtime": self.runtime.summary(),
        }

    def _log(self, kind: str, result: TaskResult) -> None:
        phase = result.data.get("phase")
        if phase is None:
            phase = getattr(getattr(self.task, "phase", None), "value", None)
        self.transitions.append(
            {
                "kind": kind,
                "task": None if self.task is None else self.task.name,
                "phase": phase,
                "status": result.status.value,
                "reason": result.reason,
            }
        )
