from __future__ import annotations

from l2_brain.io.actions import HoldKey, SkillActivate
from l2_brain.live.skills.base import BaseSkill
from l2_brain.live.skills.dispatch import send_live
from l2_brain.live.skills.result import SkillResult, SkillStatus
from l2_brain.live.world_state import WorldState


class TapHotkey(BaseSkill):
    """One SkillActivate tap. F5 path must not go through OpenNpcDialog (that skill sends F2)."""

    name = "tap_hotkey"

    def __init__(self, key: str = "F5", slot: int | None = None) -> None:
        super().__init__()
        self.key = str(key)
        if slot is not None:
            self.slot = int(slot)
        elif self.key.startswith("F") and self.key[1:].isdigit():
            self.slot = int(self.key[1:])
        else:
            self.slot = 0

    def start(self, context: object, state: WorldState) -> SkillResult:
        if not self.can_start(state):
            return self._fail("precondition")
        ev = send_live(
            context.backend,
            SkillActivate(slot=self.slot, key=self.key, duration_ms=40),
            context.log,
        )
        if ev is None:
            return self._fail(str(context.log.get("aborted") or "tap_failed"), key=self.key)
        return self._ok("tapped", key=self.key, slot=self.slot)

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self._status is SkillStatus.READY:
            return self._fail("not_started")
        return SkillResult(self._status, reason="already_finished")


class CloseDialog(BaseSkill):
    """One Escape. SUCCESS if the next observation has dialog_open is not True."""

    name = "close_dialog"

    def start(self, context: object, state: WorldState) -> SkillResult:
        if not state.focus_ok:
            return self._fail("precondition")
        down = send_live(context.backend, HoldKey(key="escape", duration_ms=40, state="down"), context.log)
        if down is None:
            return self._fail(str(context.log.get("aborted") or "escape_failed"))
        up = send_live(context.backend, HoldKey(key="escape", duration_ms=0, state="up"), context.log)
        if up is None:
            return self._fail(str(context.log.get("aborted") or "escape_failed"))
        return self._run("escape_sent")

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self._status is not SkillStatus.RUNNING:
            return SkillResult(self._status, reason="not_running")
        if state.dialog_open is True:
            return self._fail("dialog_still_open")
        return self._ok("dialog_closed_or_absent")
