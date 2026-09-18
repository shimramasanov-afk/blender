"""Open then close Newbie Guide dialog. Not a quest. No combat skills."""

from __future__ import annotations

from enum import Enum

from l2_brain.live.runtime import LiveRuntime
from l2_brain.live.skills.result import SkillStatus
from l2_brain.live.tasks.base import BaseTask
from l2_brain.live.tasks.result import TaskResult, TaskStatus
from l2_brain.live.world_state import WorldState

OPEN_SKILL = "open_npc_dialog"
CLOSE_SKILL = "close_dialog"
MAX_OPEN_ATTEMPTS = 2

_RETRY_REASONS = frozenset(
    {
        "dialog_timeout",
        "approach_unconfirmed",
        "talk_click_failed",
        "f2_failed",
        "no_target",
        "chat_target_failed",
        "precondition",
        "targeting",
        "dialog_still_open",
    }
)
_ABORT_REASONS = frozenset(
    {
        "focus_lost",
        "capture_lost",
        "kill_switch",
        "exception",
        "shutdown",
        "operator_cancel",
    }
)


class GuidePhase(Enum):
    READY = "ready"
    TARGET_AND_OPEN = "target_and_open"
    VERIFY_OPEN = "verify_open"
    CLOSE = "close"
    VERIFY_CLOSED = "verify_closed"
    SUCCESS = "success"


class GuideInteractionTask(BaseTask):
    name = "guide_open_close"

    def __init__(self, npc_name: str = "Newbie Guide") -> None:
        super().__init__()
        self.npc_name = npc_name
        self.phase = GuidePhase.READY
        self.open_attempts = 0
        self._recovering = False

    def start(self, runtime: LiveRuntime, state: WorldState) -> TaskResult:
        if self._status is not TaskStatus.READY:
            return self._result(self._status, "already_started", phase=self.phase.value)
        return self._begin_open(runtime, state)

    def tick(self, runtime: LiveRuntime, state: WorldState) -> TaskResult:
        if self._status is TaskStatus.READY:
            return self._result(TaskStatus.FAILED, "not_started")
        if self._status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.ABORTED):
            return self._result(self._status, None if runtime.last_result is None else runtime.last_result.reason)
        aborted = self._aborted(runtime)
        if aborted is not None:
            return aborted
        last = runtime.last_result
        if self.phase is GuidePhase.TARGET_AND_OPEN:
            return self._on_open(runtime, state, last)
        if self.phase is GuidePhase.VERIFY_OPEN:
            return self._verify_open(runtime, state)
        if self.phase is GuidePhase.CLOSE:
            return self._on_close(runtime, state, last)
        if self.phase is GuidePhase.VERIFY_CLOSED:
            return self._verify_closed(state)
        return self._result(TaskStatus.FAILED, "unknown_phase", phase=self.phase.value)

    def _begin_open(self, runtime: LiveRuntime, state: WorldState) -> TaskResult:
        if self.open_attempts >= MAX_OPEN_ATTEMPTS:
            self._note(state=self.phase.value, result="FAILED", why="retry_exhausted")
            return self._result(TaskStatus.FAILED, "retry_exhausted", attempts=self.open_attempts)
        self.open_attempts += 1
        self.phase = GuidePhase.TARGET_AND_OPEN
        self._recovering = False
        skill = runtime.start_skill(OPEN_SKILL, npc_name=self.npc_name)
        self._note(
            state=self.phase.value,
            skill=OPEN_SKILL,
            result=skill.status.value,
            reason=skill.reason,
            attempt=self.open_attempts,
        )
        if skill.status is SkillStatus.ABORTED:
            return self._abort(skill.reason or "aborted")
        if skill.status is SkillStatus.SUCCESS:
            return self._verify_open(runtime, runtime.state)
        if skill.status is SkillStatus.FAILED:
            return self._recover_or_fail(runtime, skill.reason)
        return self._result(TaskStatus.RUNNING, skill.reason, phase=self.phase.value, attempt=self.open_attempts)

    def _on_open(self, runtime: LiveRuntime, state: WorldState, last) -> TaskResult:
        if last is None or last.status is SkillStatus.RUNNING:
            self._note(state=self.phase.value, skill=OPEN_SKILL, result="RUNNING")
            return self._result(TaskStatus.RUNNING, None if last is None else last.reason, phase=self.phase.value)
        self._note(state=self.phase.value, skill=OPEN_SKILL, result=last.status.value, reason=last.reason)
        if last.status is SkillStatus.ABORTED:
            return self._abort(last.reason or "aborted")
        if last.status is SkillStatus.SUCCESS:
            return self._verify_open(runtime, state)
        if last.status is SkillStatus.FAILED:
            return self._recover_or_fail(runtime, last.reason)
        return self._result(TaskStatus.FAILED, last.reason or "open_failed")

    def _verify_open(self, runtime: LiveRuntime, state: WorldState) -> TaskResult:
        self.phase = GuidePhase.VERIFY_OPEN
        if state.dialog_open is not True:
            self._note(state=self.phase.value, result="FAILED", why="dialog_not_open")
            return self._recover_or_fail(runtime, "dialog_not_open")
        self._note(state=self.phase.value, result="SUCCESS")
        return self._begin_close(runtime, recovery=False)

    def _begin_close(self, runtime: LiveRuntime, *, recovery: bool) -> TaskResult:
        self.phase = GuidePhase.CLOSE
        self._recovering = recovery
        skill = runtime.start_skill(CLOSE_SKILL)
        self._note(
            state=self.phase.value,
            skill=CLOSE_SKILL,
            result=skill.status.value,
            reason=skill.reason,
            recovery=recovery,
        )
        if skill.status is SkillStatus.ABORTED:
            return self._abort(skill.reason or "aborted")
        if skill.status is SkillStatus.SUCCESS:
            return self._after_close(runtime, runtime.state)
        if skill.status is SkillStatus.FAILED:
            return self._after_close_failed(runtime, skill.reason)
        return self._result(TaskStatus.RUNNING, skill.reason, phase=self.phase.value)

    def _on_close(self, runtime: LiveRuntime, state: WorldState, last) -> TaskResult:
        if last is None or last.status is SkillStatus.RUNNING:
            self._note(state=self.phase.value, skill=CLOSE_SKILL, result="RUNNING")
            return self._result(TaskStatus.RUNNING, None if last is None else last.reason, phase=self.phase.value)
        self._note(
            state=self.phase.value,
            skill=CLOSE_SKILL,
            result=last.status.value,
            reason=last.reason,
            recovery=self._recovering,
        )
        if last.status is SkillStatus.ABORTED:
            return self._abort(last.reason or "aborted")
        if last.status is SkillStatus.SUCCESS:
            return self._after_close(runtime, state)
        return self._after_close_failed(runtime, last.reason)

    def _after_close(self, runtime: LiveRuntime, state: WorldState) -> TaskResult:
        if self._recovering:
            return self._begin_open(runtime, state)
        return self._verify_closed(state)

    def _after_close_failed(self, runtime: LiveRuntime, reason: str | None) -> TaskResult:
        if self._recovering:
            return self._begin_open(runtime, runtime.state)
        return self._result(TaskStatus.FAILED, reason or "close_failed", phase=self.phase.value)

    def _verify_closed(self, state: WorldState) -> TaskResult:
        self.phase = GuidePhase.VERIFY_CLOSED
        if state.dialog_open is True:
            self._note(state=self.phase.value, result="FAILED", why="dialog_still_open")
            return self._result(TaskStatus.FAILED, "dialog_still_open")
        self.phase = GuidePhase.SUCCESS
        self._note(state=self.phase.value, result="SUCCESS")
        return self._result(TaskStatus.SUCCESS, "guide_open_close_done", attempts=self.open_attempts)

    def _recover_or_fail(self, runtime: LiveRuntime, reason: str | None) -> TaskResult:
        if reason in _ABORT_REASONS:
            return self._abort(reason)
        if self.open_attempts < MAX_OPEN_ATTEMPTS and (reason in _RETRY_REASONS or reason == "dialog_not_open"):
            self._note(state=self.phase.value, result="RETRY", reason=reason, attempt=self.open_attempts)
            return self._begin_close(runtime, recovery=True)
        self._note(state=self.phase.value, result="FAILED", reason=reason, attempts=self.open_attempts)
        why = "retry_exhausted" if self.open_attempts >= MAX_OPEN_ATTEMPTS else (reason or "open_failed")
        return self._result(TaskStatus.FAILED, why, attempts=self.open_attempts)

    def _aborted(self, runtime: LiveRuntime) -> TaskResult | None:
        last = runtime.last_result
        reason = None if last is None else last.reason
        if last is not None and last.status is SkillStatus.ABORTED:
            return self._abort(reason or "aborted")
        if reason in _ABORT_REASONS:
            return self._abort(reason)
        return None

    def _abort(self, reason: str) -> TaskResult:
        self._note(state=self.phase.value, result="ABORTED", reason=reason)
        return self._result(TaskStatus.ABORTED, reason, phase=self.phase.value)
