"""Thin send through the existing CGEvent backend. Not a second HID stack."""

from __future__ import annotations

from typing import Any

from l2_brain.io.actions import GameAction
from l2_brain.io.cgevent_backend import CGEventInputBackend


def send_live(backend: CGEventInputBackend, action: GameAction, log: dict[str, Any]) -> Any | None:
    """Same accept/kill-switch rules as `s4_probe._send`. Does not post events itself."""
    event = backend.send_action(action)
    log["hid_sent"] = bool(log.get("hid_sent") or event.hid_sent)
    if event.reason == "kill_switch":
        log["aborted"] = "kill_switch"
        return None
    if not event.accepted:
        log["aborted"] = event.reason
        return None
    return event
