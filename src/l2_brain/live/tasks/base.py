from __future__ import annotations

from typing import Protocol

from l2_brain.live.runtime import LiveRuntime
from l2_brain.live.tasks.result import TaskResult, TaskStatus
from l2_brain.live.world_state import WorldState


class Task(Protocol):
    name: str

    def start(self, runtime: LiveRuntime, state: WorldState) -> TaskResult: ...

    def tick(self, runtime: LiveRuntime, state: WorldState) -> TaskResult: ...

    def cancel(self, runtime: LiveRuntime, reason: str) -> TaskResult: ...


class BaseTask:
    name = "base"

    def __init__(self) -> None:
        self._status = TaskStatus.READY
        self.trace: list[dict[str, object]] = []

    def cancel(self, runtime: LiveRuntime, reason: str) -> TaskResult:
        if runtime.active_skill is not None:
            runtime.cancel_skill(reason)
        self._note(state=getattr(getattr(self, "phase", None), "value", None), result="ABORTED", reason=reason)
        return self._result(TaskStatus.ABORTED, reason)

    def _result(self, status: TaskStatus, reason: str | None = None, **data: object) -> TaskResult:
        self._status = status
        return TaskResult(status, reason=reason, data=dict(data))

    def _note(self, **row: object) -> None:
        self.trace.append(dict(row))
