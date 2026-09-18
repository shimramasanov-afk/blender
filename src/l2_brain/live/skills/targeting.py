from __future__ import annotations

from l2_brain.io.actions import TargetMethod, TargetSelect
from l2_brain.io.chat_commander import target_by_name
from l2_brain.live.skills.base import BaseSkill
from l2_brain.live.skills.dispatch import send_live
from l2_brain.live.skills.result import SkillResult, SkillStatus
from l2_brain.live.spot_loop import SCAN_S
from l2_brain.live.world_state import WorldState

CHAT_LOCK_WAIT_S = 2.0


class TargetNext(BaseSkill):
    """F1 /targetnext. SUCCESS only when WorldState reports a lock."""

    name = "target_next"

    def __init__(self, wait_s: float = SCAN_S, *, wait: bool = True) -> None:
        super().__init__()
        self._wait_s = float(wait_s)
        self._wait = bool(wait)
        self._deadline_ns: int | None = None

    def start(self, context: object, state: WorldState) -> SkillResult:
        if not self.can_start(state):
            return self._fail("precondition")
        ev = send_live(context.backend, TargetSelect(method=TargetMethod.NEXT_HOTKEY), context.log)
        if ev is None:
            return self._fail(str(context.log.get("aborted") or "f1_failed"))
        if not self._wait:
            return self._ok("f1_sent")
        self._deadline_ns = context.clock() + int(self._wait_s * 1_000_000_000)
        if state.target_locked is True:
            return self._ok("already_locked")
        return self._run("waiting_lock")

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self._status is not SkillStatus.RUNNING:
            return SkillResult(self._status, reason="not_running")
        if not state.focus_ok:
            return self.cancel(context, "focus_lost")
        if not state.capture_ok:
            return self.cancel(context, "capture_lost")
        if state.target_locked is True:
            return self._ok("target_locked", target_hp=state.target_hp)
        if self._deadline_ns is not None and context.clock() >= self._deadline_ns:
            return self._fail("no_target")
        return self._run("waiting_lock")


class TargetByName(BaseSkill):
    """Uses `chat_commander.target_by_name`. That helper is still blocking (~lock wait)."""

    name = "target_by_name"

    def __init__(self, npc_name: str) -> None:
        super().__init__()
        self.npc_name = npc_name

    def start(self, context: object, state: WorldState) -> SkillResult:
        if not self.can_start(state):
            return self._fail("precondition")

        def lock_probe() -> bool:
            reader = getattr(context, "read_world", None)
            seen = reader() if callable(reader) else context.perception.observe()
            log = context.log
            log["lock_probe_frames"] = int(log.get("lock_probe_frames") or 0) + 1
            if seen.capture_ok:
                log["lock_probe_capture_ok"] = int(log.get("lock_probe_capture_ok") or 0) + 1
            return bool(seen.capture_ok and seen.target_locked is True)

        ok = target_by_name(
            context.backend,
            self.npc_name,
            lock_probe=lock_probe,
            sleeper=context.sleeper,
            now_ns=context.clock,
            payload=context.log,
            lock_wait_s=CHAT_LOCK_WAIT_S,
        )
        if ok:
            return self._ok("chat_target_success", npc_name=self.npc_name)
        return self._fail(str(context.log.get("aborted") or "chat_target_failed"), npc_name=self.npc_name)

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self._status is SkillStatus.READY:
            return self._fail("not_started")
        return SkillResult(self._status, reason="already_finished")
