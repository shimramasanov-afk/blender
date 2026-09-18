"""Live CGEvent actuator. ADR-0043. Not DryRun. Not a game client."""

from __future__ import annotations

import time
from collections.abc import Callable
from ctypes import CDLL, Structure, c_bool, c_double, c_int32, c_int64, c_uint32, c_void_p
from ctypes.util import find_library
from typing import Any, Protocol

from l2_brain.experiment.clocks import mono_ns
from l2_brain.io.actions import (
    CameraRotate,
    EmergencyStop,
    GameAction,
    GroundClick,
    HoldKey,
    InputEvent,
    MouseButton,
    SkillActivate,
    TargetSelect,
)
from l2_brain.io.backend import InputBackend, _hold_key, describe_action
from l2_brain.io.focus import PARALLELS_BUNDLES, is_allowed_frontmost
from l2_brain.io.keycodes import virtual_keycode
from l2_brain.io.profile import GameInputProfile
from l2_brain.io.safety import InputWatchdog

KCG_HID_EVENT_TAP = 0
KCG_EVENT_SOURCE_HID = 1
KCG_LEFT_DOWN = 1
KCG_LEFT_UP = 2
KCG_RIGHT_DOWN = 3
KCG_RIGHT_UP = 4
KCG_MOUSE_MOVED = 5
KCG_RIGHT_DRAGGED = 7
KCG_BUTTON_LEFT = 0
KCG_BUTTON_RIGHT = 1
KCG_MOUSE_BUTTON_NUMBER = 3
KCG_MOUSE_DELTA_X = 4
KCG_MOUSE_DELTA_Y = 5


class LiveInputNotConfirmed(RuntimeError):
    """Raised when CGEventInputBackend is constructed without live_confirmed."""


class CGPoint(Structure):
    _fields_ = [("x", c_double), ("y", c_double)]


class EventPoster(Protocol):
    def key(self, virtual_key: int, down: bool, pid: int) -> None: ...

    def mouse(
        self, event_type: int, x: float, y: float, button: int, pid: int, hid_also: bool = True
    ) -> None: ...

    def cursor(self) -> tuple[float, float]: ...

    def key_is_down(self, virtual_key: int) -> bool: ...


class RecordingPoster:
    """Test double. Does not call CoreGraphics."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def key(self, virtual_key: int, down: bool, pid: int) -> None:
        self.calls.append(("key", virtual_key, down, pid))

    def mouse(
        self, event_type: int, x: float, y: float, button: int, pid: int, hid_also: bool = True
    ) -> None:
        self.calls.append(("mouse", event_type, x, y, button, pid, hid_also))

    def cursor(self) -> tuple[float, float]:
        return (0.0, 0.0)

    def key_is_down(self, virtual_key: int) -> bool:
        return False


class QuartzPoster:
    def __init__(self) -> None:
        lib = find_library("CoreGraphics") or find_library("ApplicationServices")
        if lib is None:
            raise RuntimeError("CoreGraphics library not found")
        self._cg = CDLL(lib)
        self._cg.CGEventCreateKeyboardEvent.restype = c_void_p
        self._cg.CGEventCreateKeyboardEvent.argtypes = [c_void_p, c_uint32, c_bool]
        self._cg.CGEventCreateMouseEvent.restype = c_void_p
        self._cg.CGEventCreateMouseEvent.argtypes = [c_void_p, c_uint32, CGPoint, c_uint32]
        self._cg.CGEventCreate.restype = c_void_p
        self._cg.CGEventCreate.argtypes = [c_void_p]
        self._cg.CGEventGetLocation.restype = CGPoint
        self._cg.CGEventGetLocation.argtypes = [c_void_p]
        self._cg.CGEventPostToPid.argtypes = [c_int32, c_void_p]
        self._cg.CGEventPost.argtypes = [c_uint32, c_void_p]
        self._cg.CFRelease.argtypes = [c_void_p]
        self._cg.CGEventSourceKeyState.argtypes = [c_uint32, c_uint32]
        self._cg.CGEventSourceKeyState.restype = c_bool
        self._cg.CGEventSourceCreate.restype = c_void_p
        self._cg.CGEventSourceCreate.argtypes = [c_uint32]
        self._cg.CGEventSetIntegerValueField.argtypes = [c_void_p, c_uint32, c_int64]
        self._source = self._cg.CGEventSourceCreate(c_uint32(KCG_EVENT_SOURCE_HID))
        self._last_mouse: tuple[float, float] | None = None

    def key(self, virtual_key: int, down: bool, pid: int) -> None:
        event = self._cg.CGEventCreateKeyboardEvent(self._source, c_uint32(virtual_key), c_bool(down))
        if not event:
            raise RuntimeError("CGEventCreateKeyboardEvent failed")
        self._post(event, pid)

    def mouse(
        self,
        event_type: int,
        x: float,
        y: float,
        button: int,
        pid: int,
        hid_also: bool = True,
    ) -> None:
        point = CGPoint(x, y)
        event = self._cg.CGEventCreateMouseEvent(self._source, c_uint32(event_type), point, c_uint32(button))
        if not event:
            raise RuntimeError("CGEventCreateMouseEvent failed")
        dx = 0.0
        dy = 0.0
        if self._last_mouse is not None:
            dx = float(x) - self._last_mouse[0]
            dy = float(y) - self._last_mouse[1]
        self._last_mouse = (float(x), float(y))
        self._cg.CGEventSetIntegerValueField(event, c_uint32(KCG_MOUSE_BUTTON_NUMBER), c_int64(int(button)))
        self._cg.CGEventSetIntegerValueField(event, c_uint32(KCG_MOUSE_DELTA_X), c_int64(int(round(dx))))
        self._cg.CGEventSetIntegerValueField(event, c_uint32(KCG_MOUSE_DELTA_Y), c_int64(int(round(dy))))
        self._post(event, pid, hid_also=hid_also)

    def cursor(self) -> tuple[float, float]:
        event = self._cg.CGEventCreate(None)
        if not event:
            return (0.0, 0.0)
        try:
            loc = self._cg.CGEventGetLocation(event)
            return (float(loc.x), float(loc.y))
        finally:
            self._cg.CFRelease(event)

    def key_is_down(self, virtual_key: int) -> bool:
        return bool(self._cg.CGEventSourceKeyState(c_uint32(KCG_EVENT_SOURCE_HID), c_uint32(virtual_key)))

    def _post(self, event: int | c_void_p, pid: int, *, hid_also: bool = False) -> None:
        try:
            if pid > 0:
                self._cg.CGEventPostToPid(c_int32(pid), event)
            if hid_also or pid <= 0:
                self._cg.CGEventPost(c_uint32(KCG_HID_EVENT_TAP), event)
        finally:
            self._cg.CFRelease(event)


class CGEventInputBackend(InputBackend):
    """Posts CGEvent to a host PID. Requires live_confirmed=True. dry_run stays on DryRunInputBackend."""

    def __init__(
        self,
        target_pid: int,
        live_confirmed: bool = False,
        *,
        live_danger_confirmed: bool = False,
        profile: GameInputProfile | None = None,
        poster: EventPoster | None = None,
        focus_probe: Callable[[], bool] | None = None,
        window_origin: tuple[float, float] = (0.0, 0.0),
        now_ns: Callable[[], int] | None = None,
        allowed_bundles: tuple[str, ...] = PARALLELS_BUNDLES,
    ) -> None:
        if not live_confirmed or not live_danger_confirmed:
            raise LiveInputNotConfirmed(
                "CGEventInputBackend requires live_confirmed=True and live_danger_confirmed=True"
            )
        if target_pid < 1:
            raise ValueError("target_pid must be a positive host PID")
        self.target_pid = target_pid
        self.live_confirmed = True
        self.dry_run = False
        self.profile = profile or GameInputProfile(target_window="parallels-desktop")
        self._now = now_ns or mono_ns
        self._poster = poster or QuartzPoster()
        self._physical = not isinstance(self._poster, RecordingPoster)
        self._allowed = allowed_bundles
        self._focus_probe = focus_probe or (lambda: is_allowed_frontmost(self._allowed))
        self.window_origin = window_origin
        self.window_size: tuple[float, float] | None = None
        self._rmb_held: tuple[float, float] | None = None
        self._killed = False
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
        if self._killed:
            return self._record(now, action, accepted=False, reason="killed", hid_sent=False)
        if self._kill_switch_down():
            return self._emergency(now, "kill_switch")
        if not self.check_window_focus():
            self.release_all()
            return self._record(now, action, accepted=False, reason="focus_lost", hid_sent=False)
        self.watchdog.heartbeat(now)
        hid = self._emit(action)
        hold = _hold_key(action)
        if hold is not None:
            self.watchdog.hold(hold)
        if isinstance(action, HoldKey) and action.state == "up":
            self.watchdog.release(action.key)
        return self._record(now, action, accepted=True, reason="cgevent", hid_sent=hid)

    def type_text(
        self,
        text: str,
        *,
        sleeper: Callable[[float], None] | None = None,
        delay_s: float = 0.025,
    ) -> InputEvent:
        """Type ASCII into the focused guest. PID-only. Shift for A–Z."""
        sleep = sleeper or time.sleep
        last: InputEvent | None = None
        for char in text:
            key, shift = _chat_key(char)
            if self._kill_switch_down():
                return self.send_action(EmergencyStop(reason="kill_switch"))
            if not self.check_window_focus():
                self.release_all()
                return self._record(
                    self._now(),
                    HoldKey(key=key, duration_ms=0, state="up"),
                    accepted=False,
                    reason="focus_lost",
                    hid_sent=False,
                )
            self.watchdog.heartbeat(self._now())
            if shift:
                self._key("shift", down=True)
            self._key(key, down=True)
            self._key(key, down=False)
            if shift:
                self._key("shift", down=False)
            last = self._record(
                self._now(),
                HoldKey(key=char, duration_ms=int(delay_s * 1000), state="tap"),
                accepted=True,
                reason="type_text",
                hid_sent=self._physical,
            )
            sleep(delay_s)
        if last is None:
            return self._record(
                self._now(),
                HoldKey(key="", duration_ms=0, state="up"),
                accepted=False,
                reason="empty_text",
                hid_sent=False,
            )
        return last

    def release_all(self) -> InputEvent:
        now = self._now()
        self.rmb_up()
        held = self.watchdog.release_all()
        for key in held:
            self._key(key, down=False)
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
            dry_run=False,
            hid_sent=bool(held) and self._physical,
        )
        self.log.append(event)
        return event

    def check_window_focus(self) -> bool:
        return bool(self._focus_probe())

    def poll_kill_switch(self) -> bool:
        return self._kill_switch_down()

    def idle_act(self) -> dict[str, Any]:
        """Focus + kill-switch poll + pump + empty release. No game keys."""
        focused = self.check_window_focus()
        killed = self.poll_kill_switch()
        self.pump()
        released = self.release_all()
        return {
            "focused": focused,
            "killed": killed,
            "hid_sent": bool(released.hid_sent),
        }

    def rotate_camera_keyboard(
        self,
        direction: str = "right",
        duration_ms: int = 400,
        *,
        sleeper: Callable[[float], None] | None = None,
        tick_s: float = 0.05,
    ) -> InputEvent:
        """Hold left/right arrow. No mouse drag. Heartbeat so the 250ms watchdog does not trip."""
        names = {
            "right": "right_arrow",
            "left": "left_arrow",
            "right_arrow": "right_arrow",
            "left_arrow": "left_arrow",
        }
        if direction not in names:
            raise ValueError(f"unsupported camera direction: {direction}")
        return self.hold_key_timed(names[direction], duration_ms, sleeper=sleeper, tick_s=tick_s)

    def rmb_drag(
        self,
        dx_pixels: float = 150.0,
        *,
        dy_pixels: float = 0.0,
        steps: int = 5,
        step_delay_s: float = 0.01,
        start_norm: tuple[float, float] = (0.50, 0.40),
        sleeper: Callable[[float], None] | None = None,
        release: bool = True,
    ) -> InputEvent:
        """RMB down + stepped drag. release=False keeps RMB down until rmb_up()."""
        sleep = sleeper or time.sleep
        n = max(int(steps), 1)
        if self._kill_switch_down():
            return self.send_action(EmergencyStop(reason="kill_switch"))
        if not self.check_window_focus():
            return self._record(
                self._now(),
                CameraRotate(int(dx_pixels), int(dy_pixels)),
                accepted=False,
                reason="focus_lost",
                hid_sent=False,
            )
        ox, oy = self.window_origin
        size = self.window_size or (0.0, 0.0)
        if size[0] >= 1 and size[1] >= 1:
            x0 = ox + float(size[0]) * float(start_norm[0])
            y0 = oy + float(size[1]) * float(start_norm[1])
        else:
            x0, y0 = self._poster.cursor()
        self.watchdog.heartbeat(self._now())
        self._poster.mouse(KCG_MOUSE_MOVED, x0, y0, KCG_BUTTON_RIGHT, self.target_pid)
        self._poster.mouse(KCG_RIGHT_DOWN, x0, y0, KCG_BUTTON_RIGHT, self.target_pid)
        x = x0
        y = y0
        for i in range(1, n + 1):
            if self._kill_switch_down():
                self._poster.mouse(KCG_RIGHT_UP, x, y, KCG_BUTTON_RIGHT, self.target_pid)
                return self.send_action(EmergencyStop(reason="kill_switch"))
            if not self.check_window_focus():
                self._poster.mouse(KCG_RIGHT_UP, x, y, KCG_BUTTON_RIGHT, self.target_pid)
                return self._record(
                    self._now(),
                    CameraRotate(int(dx_pixels), int(dy_pixels)),
                    accepted=False,
                    reason="focus_lost",
                    hid_sent=False,
                )
            x = x0 + float(dx_pixels) * (i / n)
            y = y0 + float(dy_pixels) * (i / n)
            self._poster.mouse(KCG_MOUSE_MOVED, x, y, KCG_BUTTON_RIGHT, self.target_pid)
            self._poster.mouse(KCG_RIGHT_DRAGGED, x, y, KCG_BUTTON_RIGHT, self.target_pid)
            self.watchdog.heartbeat(self._now())
            sleep(step_delay_s)
        self._rmb_held = (x, y)
        if release:
            self.rmb_up()
        self.watchdog.heartbeat(self._now())
        return self._record(
            self._now(),
            CameraRotate(int(round(dx_pixels)), int(round(dy_pixels))),
            accepted=True,
            reason="rmb_drag_steps" if release else "rmb_drag_hold",
            hid_sent=self._physical,
        )

    def rmb_up(self) -> None:
        pos = self._rmb_held
        if pos is None:
            return
        x, y = pos
        self._poster.mouse(KCG_RIGHT_UP, x, y, KCG_BUTTON_RIGHT, self.target_pid)
        self._rmb_held = None
        self.watchdog.heartbeat(self._now())

    def arrow_pulse(
        self,
        key: str = "right_arrow",
        *,
        taps: int = 10,
        interval_s: float = 0.04,
        sleeper: Callable[[float], None] | None = None,
    ) -> InputEvent:
        """Discrete down/up taps. Does not rely on OS key-repeat."""
        sleep = sleeper or time.sleep
        last: InputEvent | None = None
        for _ in range(max(int(taps), 1)):
            down = self.send_action(HoldKey(key=key, duration_ms=0, state="down"))
            if not down.accepted:
                return down
            up = self.send_action(HoldKey(key=key, duration_ms=0, state="up"))
            last = up
            if not up.accepted:
                return up
            self.watchdog.heartbeat(self._now())
            sleep(interval_s)
        assert last is not None
        return last

    def hold_key_timed(
        self,
        key: str,
        duration_ms: int,
        *,
        sleeper: Callable[[float], None] | None = None,
        tick_s: float = 0.05,
        cap_ms: int = 500,
    ) -> InputEvent:
        """Hold a key. Heartbeat so the 250ms watchdog does not trip."""
        hold_ms = min(max(int(duration_ms), 1), max(int(cap_ms), 1))
        sleep = sleeper or time.sleep
        down = self.send_action(HoldKey(key=key, duration_ms=hold_ms, state="down"))
        if not down.accepted:
            return down
        until = self._now() + int(hold_ms * 1_000_000)
        while self._now() < until:
            if self._kill_switch_down():
                return self.send_action(EmergencyStop(reason="kill_switch"))
            if not self.check_window_focus():
                self.release_all()
                return self._record(
                    self._now(),
                    HoldKey(key=key, state="up"),
                    accepted=False,
                    reason="focus_lost",
                    hid_sent=False,
                )
            self.watchdog.heartbeat(self._now())
            sleep(tick_s)
        self.watchdog.heartbeat(self._now())
        return self.send_action(HoldKey(key=key, state="up"))

    def pump(self, now_ns: int | None = None) -> bool:
        now = int(now_ns if now_ns is not None else self._now())
        return self.watchdog.check(now)

    def events(self) -> list[dict[str, Any]]:
        return [row.to_dict() for row in self.log]

    def _emit(self, action: GameAction) -> bool:
        if isinstance(action, HoldKey):
            self._key(action.key, down=action.state != "up")
            return True
        if isinstance(action, SkillActivate):
            self._key(action.key, down=True)
            self._key(action.key, down=False)
            return True
        if isinstance(action, TargetSelect):
            key = self.profile.next_target_key
            self._key(key, down=True)
            self._key(key, down=False)
            return True
        if isinstance(action, GroundClick):
            ox, oy = self.window_origin
            x = ox + float(action.x)
            y = oy + float(action.y)
            x, y = _clamp_window_point(x, y, ox, oy, self.window_size)
            down, up, button = _mouse_pair(action.button)
            self._poster.mouse(KCG_MOUSE_MOVED, x, y, button, self.target_pid, hid_also=True)
            self._poster.mouse(down, x, y, button, self.target_pid, hid_also=True)
            self._poster.mouse(up, x, y, button, self.target_pid, hid_also=True)
            return True
        if isinstance(action, CameraRotate):
            cx, cy = self._poster.cursor()
            nx, ny = cx + float(action.dx_pixels), cy + float(action.dy_pixels)
            self._poster.mouse(KCG_RIGHT_DOWN, cx, cy, KCG_BUTTON_RIGHT, self.target_pid)
            self._poster.mouse(KCG_RIGHT_DRAGGED, nx, ny, KCG_BUTTON_RIGHT, self.target_pid)
            self._poster.mouse(KCG_RIGHT_UP, nx, ny, KCG_BUTTON_RIGHT, self.target_pid)
            return True
        return False

    def _key(self, name: str, *, down: bool) -> None:
        self._poster.key(virtual_keycode(name), down, self.target_pid)

    def _kill_switch_down(self) -> bool:
        try:
            return self._poster.key_is_down(virtual_keycode(self.profile.kill_switch))
        except KeyError:
            return False

    def _emergency(self, now: int, reason: str) -> InputEvent:
        self._killed = True
        held = self.watchdog.release_all()
        for key in held:
            self._key(key, down=False)
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
            dry_run=False,
            hid_sent=bool(held) and self._physical,
        )
        self.log.append(event)
        return event

    def _watchdog_release(self, held: tuple[str, ...]) -> None:
        for key in held:
            self._key(key, down=False)
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
                dry_run=False,
                hid_sent=self._physical,
            )
        )

    def _record(
        self,
        now: int,
        action: GameAction,
        *,
        accepted: bool,
        reason: str,
        hid_sent: bool,
    ) -> InputEvent:
        event = describe_action(
            action,
            now,
            self.profile.target_window,
            accepted=accepted,
            reason=reason,
            dry_run=False,
            hid_sent=hid_sent and accepted and self._physical,
        )
        self.log.append(event)
        return event


def _mouse_pair(button: MouseButton) -> tuple[int, int, int]:
    if button is MouseButton.RIGHT:
        return KCG_RIGHT_DOWN, KCG_RIGHT_UP, KCG_BUTTON_RIGHT
    return KCG_LEFT_DOWN, KCG_LEFT_UP, KCG_BUTTON_LEFT


def _clamp_window_point(
    x: float,
    y: float,
    origin_x: float,
    origin_y: float,
    size: tuple[float, float] | None,
) -> tuple[float, float]:
    if size is None or size[0] < 8 or size[1] < 8:
        return (x, y)
    x1 = origin_x + float(size[0]) - 3.0
    y1 = origin_y + float(size[1]) - 3.0
    return (
        min(max(origin_x + 2.0, x), x1),
        min(max(origin_y + 2.0, y), y1),
    )


def _chat_key(char: str) -> tuple[str, bool]:
    if char == " ":
        return "space", False
    if char == "/":
        return "slash", False
    if char == "-":
        return "-", False
    if "0" <= char <= "9":
        return char, False
    if "a" <= char <= "z":
        return char, False
    if "A" <= char <= "Z":
        return char.lower(), True
    raise KeyError(f"unsupported chat char: {char!r}")
