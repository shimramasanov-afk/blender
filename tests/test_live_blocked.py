from __future__ import annotations

import pytest

from l2_brain.actuators.live import LiveHIDActuator
from l2_brain.capture.screencapturekit import ScreenCaptureKitSource
from l2_brain.env.live import LiveClientEnv
from l2_brain.safety import FORBIDDEN
from l2_brain.types import Action


def test_live_client_is_blocked() -> None:
    with pytest.raises(NotImplementedError):
        LiveClientEnv().reset()


def test_screencapture_source_is_blocked() -> None:
    with pytest.raises(NotImplementedError):
        ScreenCaptureKitSource().start()


def test_live_hid_is_blocked() -> None:
    with pytest.raises(NotImplementedError):
        LiveHIDActuator().apply(Action(0.0, 0.0, 0.0))


def test_forbidden_capabilities_are_named() -> None:
    assert "anticheat_bypass" in FORBIDDEN
    assert "credential_interception" in FORBIDDEN
