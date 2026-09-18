from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from l2_brain.experiment.clocks import mono_ns
from l2_brain.io.actions import (
    CameraRotate,
    EmergencyStop,
    GameAction,
    GroundClick,
    HoldKey,
    InputEvent,
    Pickup,
    SkillActivate,
    TargetSelect,
)
from l2_brain.io.profile import GameInputProfile
from l2_brain.io.safety import InputWatchdog
from l2_brain.safety import LIVE_CLIENT_BLOCKED_REASON


class InputBackend(ABC):
    """Game-facing adapter. Default is dry-run. Not circuit.protocols.InputBackend."""

    dry_run: bool = True

    @abstractmethod
    def send_action(self, action: GameAction) -> InputEvent: ...

    @abstractmethod
    def release_all(self) -> InputEvent: ...

    @abstractmethod
    def check_window_focus(self) -> bool: ...


class DryRunInputBackend(InputBackend):
    """Logs virtual events. Never sends HID. live=False is the only supported mode."""

    def __init__(
        self,
        profile: GameInputProfile | None = None,
        *,
        dry_run: bool = True,
        now_ns: Callable[[], int] | None = None,
    ) -> None:
        if not dry_run:
            raise NotImplementedError(
                "Живой ввод закрыт. Только dry-run. " + LIVE_CLIENT_BLOCKED_REASON
            )
        self.dry_run = True
        self.profile = profile or GameInputProfile()
        self._now = now_ns or mono_ns
        self.focus_lost = False
        self.log: list[InputEvent] = []
        self.watchdog = InputWatchdog(
            self.profile.watchdog_timeout_ms,
            now_ns=self._now,
            on_release=self._watchdog_release,
        )

    def send_action(self, action: GameAction) -> InputEvent:
        now = self._now()
        self.watchdog.check(now)
        if isinstance(action, EmergencyStop):
            return self._emergency(now, action.reason)
        if not self.check_window_focus():
            self.release_all()
            return self._record(now, action, accepted=False, reason="focus_lost")
        self.watchdog.heartbeat(now)
        hold = _hold_key(action)
        if hold is not None:
            self.watchdog.hold(hold)
        return self._record(now, action, accepted=True, reason="dry_run")

    def release_all(self) -> InputEvent:
        now = self._now()
        held = self.watchdog.release_all()
        event = InputEvent(
            timestamp_ns=now,
            action_type="release_all",
            key=",".join(held) if held else None,
            button=None,
            hold_duration_ms=0,
            target_window=self.profile.target_window,
            dx=None,
            dy=None,
            x=None,
            y=None,
            accepted=True,
            reason="release_all",
        )
        self.log.append(event)
        return event

    def check_window_focus(self) -> bool:
        return not self.focus_lost

    def pump(self, now_ns: int | None = None) -> bool:
        now = int(now_ns if now_ns is not None else self._now())
        return self.watchdog.check(now)

    def events(self) -> list[dict[str, Any]]:
        return [row.to_dict() for row in self.log]

    def _emergency(self, now: int, reason: str) -> InputEvent:
        self.watchdog.release_all()
        event = InputEvent(
            timestamp_ns=now,
            action_type=EmergencyStop.__name__,
            key=self.profile.kill_switch,
            button=None,
            hold_duration_ms=0,
            target_window=self.profile.target_window,
            dx=None,
            dy=None,
            x=None,
            y=None,
            accepted=True,
            reason=reason,
        )
        self.log.append(event)
        return event

    def _watchdog_release(self, held: tuple[str, ...]) -> None:
        self.log.append(
            InputEvent(
                timestamp_ns=self._now(),
                action_type="release_all",
                key=",".join(held),
                button=None,
                hold_duration_ms=0,
                target_window=self.profile.target_window,
                dx=None,
                dy=None,
                x=None,
                y=None,
                accepted=True,
                reason="watchdog_timeout",
            )
        )

    def _record(self, now: int, action: GameAction, *, accepted: bool, reason: str) -> InputEvent:
        event = describe_action(action, now, self.profile.target_window, accepted=accepted, reason=reason)
        self.log.append(event)
        return event


def describe_action(
    action: GameAction,
    timestamp_ns: int,
    target_window: str,
    *,
    accepted: bool,
    reason: str,
    dry_run: bool = True,
    hid_sent: bool = False,
) -> InputEvent:
    key = None
    button = None
    hold = None
    dx = dy = x = y = None
    if isinstance(action, CameraRotate):
        dx, dy = action.dx_pixels, action.dy_pixels
        button = "right"
        hold = 0
    elif isinstance(action, GroundClick):
        x, y = action.x, action.y
        button = str(action.button)
        hold = 0
    elif isinstance(action, TargetSelect):
        key = action.method.value
        if action.coords is not None:
            x, y = action.coords
            button = "left"
    elif isinstance(action, SkillActivate):
        key = action.key
        hold = action.duration_ms
    elif isinstance(action, HoldKey):
        key = action.key
        hold = action.duration_ms
    elif isinstance(action, EmergencyStop):
        key = "kill_switch"
        hold = 0
    elif isinstance(action, Pickup):
        key = f"loot:{action.entity_id}"
        hold = 0
    return InputEvent(
        timestamp_ns=timestamp_ns,
        action_type=type(action).__name__,
        key=key,
        button=button,
        hold_duration_ms=hold,
        target_window=target_window,
        dx=dx,
        dy=dy,
        x=x,
        y=y,
        accepted=accepted,
        reason=reason,
        dry_run=dry_run,
        hid_sent=hid_sent,
    )


def _hold_key(action: GameAction) -> str | None:
    if isinstance(action, HoldKey) and action.state == "down" and action.duration_ms == 0:
        return action.key
    return None
