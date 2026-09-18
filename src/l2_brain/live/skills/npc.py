from __future__ import annotations

from l2_brain.io.actions import GroundClick, MouseButton, SkillActivate
from l2_brain.live.npc_dialog_probe import APPROACH_S, TALK_NX, TALK_NY, TALK_WAIT_S
from l2_brain.live.skills.base import BaseSkill
from l2_brain.live.skills.dispatch import send_live
from l2_brain.live.skills.result import SkillResult, SkillStatus
from l2_brain.live.skills.targeting import TargetByName
from l2_brain.live.world_state import WorldState


def _click_norm(context: object, state: WorldState, nx: float, ny: float) -> tuple[int, int] | None:
    if context.window_size is not None:
        win_w, win_h = context.window_size
    elif state.frame_width and state.frame_height:
        win_w, win_h = state.frame_width, state.frame_height
    else:
        context.log["aborted"] = "no_frame_size"
        return None
    cx = int(nx * win_w)
    cy = int(ny * win_h)
    ev = send_live(context.backend, GroundClick(x=cx, y=cy, button=MouseButton.LEFT), context.log)
    if ev is None:
        return None
    return cx, cy


class ApproachNamedNpc(BaseSkill):
    """F2 after a named lock. Timer alone is not SUCCESS (no distance signal)."""

    name = "approach_named_npc"

    def __init__(self) -> None:
        super().__init__()
        self._deadline_ns: int | None = None

    def can_start(self, state: WorldState) -> bool:
        return super().can_start(state) and state.target_locked is True

    def start(self, context: object, state: WorldState) -> SkillResult:
        if not self.can_start(state):
            return self._fail("precondition")
        ev = send_live(context.backend, SkillActivate(slot=2, key="F2", duration_ms=40), context.log)
        if ev is None:
            return self._fail(str(context.log.get("aborted") or "f2_failed"))
        self._deadline_ns = context.clock() + int(APPROACH_S * 1_000_000_000)
        return self._run("approaching")

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self._status is not SkillStatus.RUNNING:
            return SkillResult(self._status, reason="not_running")
        if not state.focus_ok:
            return self.cancel(context, "focus_lost")
        if state.dialog_open is True:
            return self._ok("dialog_appeared")
        if self._deadline_ns is not None and context.clock() >= self._deadline_ns:
            return self._fail("approach_unconfirmed", note="no_distance_or_dialog_signal")
        return self._run("approaching")


class OpenNpcDialog(BaseSkill):
    """F85 path as ticks: TargetByName → F2 → wait → click 0.50/0.48 → wait HTML."""

    name = "open_npc_dialog"

    def __init__(self, npc_name: str = "Newbie Guide", *, retarget: bool = True) -> None:
        super().__init__()
        self.npc_name = npc_name
        self.retarget = bool(retarget)
        self._step = 0
        self._child: TargetByName | None = None
        self._wait_until: int | None = None
        self._f2 = False
        self._talk = False
        self._talk_xy: tuple[int, int] | None = None

    def start(self, context: object, state: WorldState) -> SkillResult:
        if not self.can_start(state):
            return self._fail("precondition")
        self._f2 = False
        self._talk = False
        self._talk_xy = None
        if not self.retarget:
            self._step = 1
            if state.dialog_open is True:
                return self._ok("dialog_open", f2_approach=False, talk_clicked=False)
            return self._run("targeted")
        self._step = 0
        self._child = TargetByName(self.npc_name)
        result = self._child.start(context, state)
        if result.status is SkillStatus.FAILED:
            return result
        if result.status is SkillStatus.SUCCESS:
            self._step = 1
            return self._run("targeted")
        return self._run("targeting")

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self._status is not SkillStatus.RUNNING:
            return SkillResult(self._status, reason="not_running")
        if not state.focus_ok:
            return self.cancel(context, "focus_lost")
        if not state.capture_ok:
            return self.cancel(context, "capture_lost")
        if state.dialog_open is True and self._step >= 1:
            return self._ok(
                "dialog_open",
                f2_approach=self._f2,
                talk_clicked=self._talk,
                x=None if self._talk_xy is None else self._talk_xy[0],
                y=None if self._talk_xy is None else self._talk_xy[1],
            )
        if self._step == 0:
            assert self._child is not None
            result = self._child.tick(context, state)
            if result.status is SkillStatus.RUNNING:
                return self._run("targeting")
            if result.status is not SkillStatus.SUCCESS:
                self._status = result.status
                return result
            self._step = 1
            return self._run("targeted")
        if self._step == 1:
            ev = send_live(context.backend, SkillActivate(slot=2, key="F2", duration_ms=40), context.log)
            if ev is None:
                return self._fail(str(context.log.get("aborted") or "f2_failed"))
            self._f2 = True
            self._wait_until = context.clock() + int(APPROACH_S * 1_000_000_000)
            self._step = 2
            return self._run("f2_approach", f2_approach=True)
        if self._step == 2:
            if self._wait_until is not None and context.clock() < self._wait_until:
                return self._run("approach_wait")
            clicked = _click_norm(context, state, TALK_NX, TALK_NY)
            if clicked is None:
                return self._fail(str(context.log.get("aborted") or "talk_click_failed"))
            self._talk = True
            self._talk_xy = clicked
            self._wait_until = context.clock() + int(TALK_WAIT_S * 1_000_000_000)
            self._step = 3
            return self._run("talk_clicked", x=clicked[0], y=clicked[1], talk_clicked=True, f2_approach=True)
        if self._wait_until is not None and context.clock() < self._wait_until:
            return self._run("wait_html")
        return self._fail("dialog_timeout")


class TalkClick(BaseSkill):
    """F5 talk click 0.50/0.48. No F2. SUCCESS when dialog_open."""

    name = "talk_click"

    def __init__(self) -> None:
        super().__init__()
        self._wait_until: int | None = None
        self._xy: tuple[int, int] | None = None

    def start(self, context: object, state: WorldState) -> SkillResult:
        if not self.can_start(state):
            return self._fail("precondition")
        clicked = _click_norm(context, state, TALK_NX, TALK_NY)
        if clicked is None:
            return self._fail(str(context.log.get("aborted") or "talk_click_failed"))
        self._xy = clicked
        self._wait_until = context.clock() + int(TALK_WAIT_S * 1_000_000_000)
        return self._run("talk_clicked", x=clicked[0], y=clicked[1], talk_clicked=True)

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self._status is not SkillStatus.RUNNING:
            return SkillResult(self._status, reason="not_running")
        if not state.focus_ok:
            return self.cancel(context, "focus_lost")
        if not state.capture_ok:
            return self.cancel(context, "capture_lost")
        if state.dialog_open is True:
            x, y = self._xy or (None, None)
            return self._ok("dialog_open", x=x, y=y, talk_clicked=True)
        if self._wait_until is not None and context.clock() >= self._wait_until:
            return self._fail("dialog_timeout")
        return self._run("wait_html")


class ClickDialogItem(BaseSkill):
    """Click a detected blue-link center by index or explicit pixels. Not AcceptQuest."""

    name = "click_dialog_item"

    def __init__(self, index: int = 0, x: int | None = None, y: int | None = None) -> None:
        super().__init__()
        self.index = int(index)
        self.x = None if x is None else int(x)
        self.y = None if y is None else int(y)

    def _xy(self, context: object, state: WorldState) -> tuple[int, int] | None:
        if self.x is not None and self.y is not None:
            return self.x, self.y
        if 0 <= self.index < len(state.dialog_items):
            x, y = state.dialog_items[self.index]
            return int(x), int(y)
        dialog = getattr(context.perception, "last_dialog", None)
        link = getattr(dialog, "first_link", None) if dialog is not None else None
        if self.index == 0 and link is not None:
            return int(link[0]), int(link[1])
        return None

    def can_start(self, state: WorldState) -> bool:
        if not super().can_start(state):
            return False
        if self.x is not None and self.y is not None:
            return True
        if 0 <= self.index < len(state.dialog_items):
            return True
        return False

    def start(self, context: object, state: WorldState) -> SkillResult:
        xy = self._xy(context, state)
        if xy is None or not super().can_start(state):
            return self._fail("precondition")
        x, y = xy
        ev = send_live(context.backend, GroundClick(x=int(x), y=int(y), button=MouseButton.LEFT), context.log)
        if ev is None:
            return self._fail(str(context.log.get("aborted") or "click_failed"))
        return self._ok("click_dispatched", x=int(x), y=int(y), index=self.index, semantic=False)

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self._status is SkillStatus.READY:
            return self._fail("not_started")
        return SkillResult(self._status, reason="already_finished")
