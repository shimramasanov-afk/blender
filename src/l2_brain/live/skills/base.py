from __future__ import annotations

from typing import Protocol

from l2_brain.live.skills.result import SkillResult, SkillStatus
from l2_brain.live.world_state import WorldState


class Skill(Protocol):
    name: str

    def can_start(self, state: WorldState) -> bool: ...

    def start(self, context: object, state: WorldState) -> SkillResult: ...

    def tick(self, context: object, state: WorldState) -> SkillResult: ...

    def cancel(self, context: object, reason: str) -> SkillResult: ...


class BaseSkill:
    name = "base"

    def __init__(self) -> None:
        self._status = SkillStatus.READY
        self._hold_key: str | None = None
        self._until_ns: int | None = None

    def can_start(self, state: WorldState) -> bool:
        return bool(state.capture_ok and state.focus_ok)

    def cancel(self, context: object, reason: str) -> SkillResult:
        backend = getattr(context, "backend", None)
        if backend is not None:
            try:
                backend.release_all()
            except Exception:  # noqa: BLE001 — cancel must finish
                pass
        self._hold_key = None
        self._until_ns = None
        self._status = SkillStatus.ABORTED
        return SkillResult(SkillStatus.ABORTED, reason=reason)

    def _fail(self, reason: str, **data: object) -> SkillResult:
        self._status = SkillStatus.FAILED
        return SkillResult(SkillStatus.FAILED, reason=reason, data=dict(data))

    def _ok(self, reason: str, **data: object) -> SkillResult:
        self._status = SkillStatus.SUCCESS
        return SkillResult(SkillStatus.SUCCESS, reason=reason, data=dict(data))

    def _run(self, reason: str | None = None, **data: object) -> SkillResult:
        self._status = SkillStatus.RUNNING
        return SkillResult(SkillStatus.RUNNING, reason=reason, data=dict(data))
