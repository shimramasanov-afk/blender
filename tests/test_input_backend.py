from __future__ import annotations

import json

from l2_brain.contracts import MotorIntent
from l2_brain.io import (
    CameraRotate,
    DryRunInputBackend,
    EmergencyStop,
    GameInputProfile,
    GroundClick,
    HoldKey,
    IntentDecoder,
    MouseButton,
)
from l2_brain.safety import LIVE_CLIENT_BLOCKED_REASON


class _Clock:
    def __init__(self) -> None:
        self.t = 1_000_000_000

    def __call__(self) -> int:
        return self.t

    def advance_ms(self, ms: int) -> None:
        self.t += ms * 1_000_000


def _intent(*, turn: float = 0.0, forward: float = 0.0, stop: str = "idle") -> MotorIntent:
    return MotorIntent(
        turn=turn,
        forward=forward,
        stop=stop,  # type: ignore[arg-type]
        select_target="idle",
        attack="idle",
        confidence=0.5,
        valid_until_ns=2_000_000_000,
    )


def test_dry_run_logs_without_hid() -> None:
    clock = _Clock()
    backend = DryRunInputBackend(now_ns=clock)
    decoder = IntentDecoder()
    for intent in (_intent(forward=0.8, turn=0.2), _intent(turn=-0.4), _intent(stop="fire")):
        for action in decoder.decode(intent):
            backend.send_action(action)
    assert backend.log
    assert all(row.dry_run and not row.hid_sent for row in backend.log)
    payload = json.dumps(backend.events())
    assert "CameraRotate" in payload
    assert "EmergencyStop" in payload
    assert all(row.get("hid_sent") is False for row in backend.events())
    assert "CGEvent" not in payload


def test_forward_and_yaw_translate() -> None:
    hold_profile = GameInputProfile(move_mode="hold_forward")
    click_profile = GameInputProfile(move_mode="ground_click")
    right = IntentDecoder(hold_profile).decode(_intent(forward=0.7, turn=0.25))
    left = IntentDecoder(hold_profile).decode(_intent(turn=-0.25))
    click = IntentDecoder(click_profile).decode(_intent(forward=0.9))
    assert any(isinstance(a, HoldKey) and a.key == "w" for a in right)
    cam_r = next(a for a in right if isinstance(a, CameraRotate))
    cam_l = next(a for a in left if isinstance(a, CameraRotate))
    assert cam_r.dx_pixels > 0
    assert cam_l.dx_pixels < 0
    assert any(isinstance(a, GroundClick) and a.button is MouseButton.LEFT for a in click)
    idle = IntentDecoder(hold_profile).decode(_intent(forward=0.2, turn=0.0))
    assert idle == []


def test_watchdog_releases_holds_after_timeout() -> None:
    clock = _Clock()
    backend = DryRunInputBackend(now_ns=clock)
    backend.send_action(HoldKey(key="w", duration_ms=0))
    assert "w" in backend.watchdog.active_holds
    clock.advance_ms(300)
    tripped = backend.pump()
    assert tripped
    assert backend.watchdog.active_holds == set()
    assert any(row.reason == "watchdog_timeout" for row in backend.log)
    assert backend.watchdog.release_count == 1


def test_focus_lost_blocks_and_releases() -> None:
    clock = _Clock()
    backend = DryRunInputBackend(now_ns=clock)
    backend.send_action(HoldKey(key="w", duration_ms=0))
    backend.focus_lost = True
    assert backend.check_window_focus() is False
    event = backend.send_action(CameraRotate(10, 0))
    assert event.accepted is False
    assert event.reason == "focus_lost"
    assert backend.watchdog.active_holds == set()


def test_live_flag_is_rejected() -> None:
    try:
        DryRunInputBackend(dry_run=False)
    except NotImplementedError as exc:
        assert LIVE_CLIENT_BLOCKED_REASON in str(exc)
    else:
        raise AssertionError("live backend must not construct")


def test_emergency_stop_clears_holds() -> None:
    backend = DryRunInputBackend(now_ns=_Clock())
    backend.send_action(HoldKey(key="w", duration_ms=0))
    backend.send_action(EmergencyStop())
    assert backend.watchdog.active_holds == set()
    assert backend.log[-1].action_type == "EmergencyStop"
