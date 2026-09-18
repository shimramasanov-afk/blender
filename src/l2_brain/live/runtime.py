"""One live process: observe → one skill → existing CGEvent backend. Not Circuit. Not a probe rename."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from l2_brain.experiment.clocks import mono_ns
from l2_brain.io.cgevent_backend import CGEventInputBackend
from l2_brain.live.perception import PerceptionHub
from l2_brain.live.s4_probe import TICK_S
from l2_brain.live.skills.base import Skill
from l2_brain.live.skills.context import SkillContext
from l2_brain.live.skills.registry import SkillRegistry, default_registry
from l2_brain.live.skills.result import SkillResult, SkillStatus
from l2_brain.live.world_state import AgentMode, WorldState, empty_world_state

_SKILL_MODE = {
    "walk_pulse": AgentMode.MOVING,
    "rotate_left": AgentMode.MOVING,
    "rotate_right": AgentMode.MOVING,
    "u_turn": AgentMode.MOVING,
    "target_next": AgentMode.COMBAT,
    "attack_target": AgentMode.COMBAT,
    "loot_target": AgentMode.COMBAT,
    "target_by_name": AgentMode.NPC_INTERACTION,
    "approach_named_npc": AgentMode.NPC_INTERACTION,
    "open_npc_dialog": AgentMode.NPC_INTERACTION,
    "click_dialog_item": AgentMode.NPC_INTERACTION,
    "talk_click": AgentMode.NPC_INTERACTION,
    "tap_hotkey": AgentMode.COMBAT,
    "close_dialog": AgentMode.RECOVERY,
}

_SAFETY_REASONS = frozenset(
    {"kill_switch", "focus_lost", "capture_lost", "exception", "shutdown", "operator_cancel"}
)


class LiveRuntime:
    def __init__(
        self,
        perception: PerceptionHub,
        *,
        backend: CGEventInputBackend | None = None,
        registry: SkillRegistry | None = None,
        clock: Callable[[], int] | None = None,
        sleeper: Callable[[float], None] | None = None,
        telemetry: Any | None = None,
        window_size: tuple[int, int] | None = None,
        log: dict[str, Any] | None = None,
        recover_capture: Callable[[], bool] | None = None,
        tick_s: float = TICK_S,
    ) -> None:
        self.perception = perception
        self.backend = backend
        self.registry = registry or default_registry()
        self._clock = clock or mono_ns
        self._sleeper = sleeper or (lambda _s: None)
        self.telemetry = telemetry
        self.window_size = window_size
        self._recover_capture = recover_capture
        self._tick_s = float(tick_s)
        self.mode = AgentMode.IDLE
        self.state: WorldState = empty_world_state(timestamp_ns=self._clock(), last_error="not_observed")
        self.active_skill: Skill | None = None
        self.last_result: SkillResult | None = None
        self.log: dict[str, Any] = log if log is not None else {"hid_sent": False, "events": []}
        self._closed = False

    def _context(self) -> SkillContext:
        return SkillContext(
            input_backend=self.backend,
            perception=self.perception,
            clock=self._clock,
            sleeper=self._sleeper,
            telemetry=self.telemetry,
            window_size=self.window_size,
            log=self.log,
            world_reader=self.observe,
        )

    def observe(self) -> WorldState:
        if self.backend is not None:
            self.backend.pump()
        self.state = self.perception.observe()
        if not self.state.capture_ok and self._recover_capture is not None:
            if self._recover_capture():
                self.state = self.perception.observe()
        return self.state

    def run_skill(self, name: str, *, on_tick: Callable[[SkillResult], bool] | None = None, **kwargs: object) -> SkillResult:
        result = self.start_skill(name, **kwargs)
        while result is not None and not result.terminal:
            if on_tick is not None and on_tick(result) is False:
                return self.last_result if self.last_result is not None else result
            self._sleeper(self._tick_s)
            result = self.tick()
        if result is None:
            return SkillResult(SkillStatus.FAILED, reason="no_active_skill")
        return result

    def start_skill(self, name: str, **kwargs: object) -> SkillResult:
        if self._closed:
            return SkillResult(SkillStatus.FAILED, reason="runtime_closed")
        if self.backend is None:
            return SkillResult(SkillStatus.FAILED, reason="no_input_backend")
        if self.active_skill is not None and self.last_result is not None and not self.last_result.terminal:
            return SkillResult(SkillStatus.FAILED, reason="skill_busy", data={"active": self.active_skill.name})
        if self.backend.poll_kill_switch():
            return self._abort("kill_switch")
        state = self.observe()
        if not state.focus_ok:
            return self._abort("focus_lost")
        if not state.capture_ok:
            return self._abort("capture_lost")
        skill = self.registry.get(name, **kwargs)
        if not skill.can_start(state):
            return SkillResult(SkillStatus.FAILED, reason="precondition", data={"skill": name})
        try:
            result = skill.start(self._context(), state)
        except Exception as exc:  # noqa: BLE001
            return self._abort("exception", detail=str(exc))
        self.active_skill = skill
        self.last_result = result
        self.mode = _SKILL_MODE.get(skill.name, AgentMode.IDLE)
        self._record(result, name)
        if result.terminal:
            self._on_terminal(result)
        return result

    def tick(self) -> SkillResult | None:
        if self._closed:
            return SkillResult(SkillStatus.FAILED, reason="runtime_closed")
        if self.backend is not None and self.backend.poll_kill_switch():
            return self._abort("kill_switch")
        try:
            state = self.observe()
        except Exception as exc:  # noqa: BLE001
            return self._abort("exception", detail=str(exc))
        if not state.focus_ok:
            return self._abort("focus_lost")
        if not state.capture_ok:
            return self._abort("capture_lost")
        if self.active_skill is None:
            self.mode = AgentMode.IDLE
            return None
        try:
            result = self.active_skill.tick(self._context(), state)
        except Exception as exc:  # noqa: BLE001
            return self._abort("exception", detail=str(exc))
        self.last_result = result
        self._record(result, self.active_skill.name)
        if result.terminal:
            self._on_terminal(result)
        return result

    def cancel_skill(self, reason: str = "operator_cancel") -> SkillResult | None:
        if self.active_skill is None:
            return None
        try:
            result = self.active_skill.cancel(self._context(), reason)
        except Exception:  # noqa: BLE001
            result = SkillResult(SkillStatus.ABORTED, reason=reason)
        self.last_result = result
        self._record(result, self.active_skill.name)
        self._release()
        self.active_skill = None
        self.mode = AgentMode.ABORTED if reason in _SAFETY_REASONS else AgentMode.IDLE
        return result

    def shutdown(self) -> None:
        if self.active_skill is not None:
            self.cancel_skill("shutdown")
        else:
            self._release()
        self._closed = True
        self.mode = AgentMode.IDLE if self.mode is not AgentMode.ABORTED else AgentMode.ABORTED

    def summary(self) -> dict[str, Any]:
        state = self.state
        return {
            "mode": self.mode.value,
            "capture_ok": state.capture_ok,
            "focus_ok": state.focus_ok,
            "active_skill": None if self.active_skill is None else self.active_skill.name,
            "last_status": None if self.last_result is None else self.last_result.status.value,
            "last_reason": None if self.last_result is None else self.last_result.reason,
            "self_hp": state.self_hp,
            "target_locked": state.target_locked,
            "dialog_open": state.dialog_open,
            "hid_sent": bool(self.log.get("hid_sent")),
            "closed": self._closed,
        }

    def _on_terminal(self, result: SkillResult) -> None:
        self._release()
        self.active_skill = None
        if result.status is SkillStatus.ABORTED or result.reason in _SAFETY_REASONS:
            self.mode = AgentMode.ABORTED
        else:
            self.mode = AgentMode.IDLE

    def _abort(self, reason: str, detail: str | None = None) -> SkillResult:
        if self.active_skill is not None:
            try:
                self.active_skill.cancel(self._context(), reason)
            except Exception:  # noqa: BLE001
                pass
        self._release()
        self.active_skill = None
        self.mode = AgentMode.ABORTED
        data: dict[str, object] = {}
        if detail:
            data["detail"] = detail
        result = SkillResult(SkillStatus.ABORTED, reason=reason, data=data)
        self.last_result = result
        self._record(result, reason)
        return result

    def _release(self) -> None:
        if self.backend is None:
            return
        try:
            self.backend.release_all()
        except Exception:  # noqa: BLE001
            pass

    def _record(self, result: SkillResult, name: str) -> None:
        row = {
            "skill": name,
            "status": result.status.value,
            "reason": result.reason,
            "data": dict(result.data),
        }
        events = self.log.setdefault("events", [])
        if isinstance(events, list):
            events.append(row)
        trace = self.log.setdefault("skill_trace", [])
        if isinstance(trace, list):
            trace.append(row)
