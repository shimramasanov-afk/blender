"""Short movement pulses. ADR-0064: no continuous w ≥8 s. Cap is SEARCH_HOLD_MAX_MS."""

from __future__ import annotations

from l2_brain.io.actions import HoldKey
from l2_brain.live.s4_probe import SEARCH_HOLD_MAX_MS
from l2_brain.live.skills.base import BaseSkill
from l2_brain.live.skills.dispatch import send_live
from l2_brain.live.skills.result import SkillResult, SkillStatus
from l2_brain.live.spot_loop import ARROW_MS, UTURN_ARROW_PULSES, UTURN_WALK_MS, UTURN_WALK_PULSES, WALK_MS
from l2_brain.live.world_state import WorldState


def _cap_ms(duration_ms: int) -> int:
    return min(max(int(duration_ms), 1), SEARCH_HOLD_MAX_MS)


class _HoldPulse(BaseSkill):
    def __init__(self, key: str, duration_ms: int, name: str) -> None:
        super().__init__()
        self.name = name
        self._key = key
        self._duration_ms = _cap_ms(duration_ms)

    def start(self, context: object, state: WorldState) -> SkillResult:
        if not self.can_start(state):
            return self._fail("precondition")
        backend = context.backend
        log = context.log
        clock = context.clock
        ev = send_live(backend, HoldKey(key=self._key, duration_ms=self._duration_ms, state="down"), log)
        if ev is None:
            return self._fail(str(log.get("aborted") or "send_failed"), key=self._key)
        self._hold_key = self._key
        self._until_ns = clock() + self._duration_ms * 1_000_000
        return self._run("holding", key=self._key, duration_ms=self._duration_ms)

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self._status is not SkillStatus.RUNNING:
            return SkillResult(self._status, reason="not_running")
        if not state.focus_ok:
            return self.cancel(context, "focus_lost")
        if not state.capture_ok:
            return self.cancel(context, "capture_lost")
        backend = context.backend
        clock = context.clock
        backend.watchdog.heartbeat(clock())
        if self._until_ns is not None and clock() < self._until_ns:
            return self._run("holding", key=self._key)
        up = send_live(backend, HoldKey(key=self._key, duration_ms=0, state="up"), context.log)
        self._hold_key = None
        if up is None:
            return self._fail(str(context.log.get("aborted") or "key_up_failed"), key=self._key)
        return self._ok("pulse_complete", key=self._key, duration_ms=self._duration_ms)


class WalkPulse(_HoldPulse):
    def __init__(self, duration_ms: int = WALK_MS) -> None:
        super().__init__("w", duration_ms, "walk_pulse")


class RotateLeft(_HoldPulse):
    def __init__(self, duration_ms: int = ARROW_MS) -> None:
        super().__init__("left_arrow", duration_ms, "rotate_left")


class RotateRight(_HoldPulse):
    def __init__(self, duration_ms: int = ARROW_MS) -> None:
        super().__init__("right_arrow", duration_ms, "rotate_right")


class UTurn(BaseSkill):
    """F82 u-turn: two arrow pulses then three short walks. One pulse per start/tick cycle."""

    name = "u_turn"

    def __init__(self, *, go_right: bool = True) -> None:
        super().__init__()
        arrow = "right_arrow" if go_right else "left_arrow"
        self._queue: list[tuple[str, int]] = (
            [(arrow, ARROW_MS)] * UTURN_ARROW_PULSES + [("w", UTURN_WALK_MS)] * UTURN_WALK_PULSES
        )
        self._index = 0
        self._pulse: _HoldPulse | None = None

    def start(self, context: object, state: WorldState) -> SkillResult:
        if not self.can_start(state):
            return self._fail("precondition")
        self._index = 0
        return self._begin_pulse(context, state)

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self._pulse is None:
            return self._fail("not_started")
        result = self._pulse.tick(context, state)
        if result.status is SkillStatus.RUNNING:
            return self._run("pulse", index=self._index, **result.data)
        if result.status is not SkillStatus.SUCCESS:
            self._status = result.status
            return result
        self._index += 1
        if self._index >= len(self._queue):
            return self._ok("uturn_complete", pulses=len(self._queue))
        return self._begin_pulse(context, state)

    def cancel(self, context: object, reason: str) -> SkillResult:
        if self._pulse is not None:
            self._pulse.cancel(context, reason)
        return super().cancel(context, reason)

    def _begin_pulse(self, context: object, state: WorldState) -> SkillResult:
        key, ms = self._queue[self._index]
        self._pulse = _HoldPulse(key, ms, f"uturn_{key}")
        result = self._pulse.start(context, state)
        if result.status is SkillStatus.FAILED:
            return result
        return self._run("pulse", index=self._index, key=key)
