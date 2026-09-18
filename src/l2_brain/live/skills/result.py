from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SkillStatus(Enum):
    READY = "ready"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class SkillResult:
    status: SkillStatus
    reason: str | None = None
    data: dict[str, object] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.status in (SkillStatus.SUCCESS, SkillStatus.FAILED, SkillStatus.ABORTED)
