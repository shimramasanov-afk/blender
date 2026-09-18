from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(Enum):
    READY = "ready"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class TaskResult:
    status: TaskStatus
    reason: str | None = None
    data: dict[str, object] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.ABORTED)
