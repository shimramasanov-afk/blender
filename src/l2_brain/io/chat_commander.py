"""Chat-line targeting. /target <Name>. Not a hotbar macro. Not farm."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from l2_brain.experiment.clocks import mono_ns
from l2_brain.io.actions import HoldKey
from l2_brain.io.cgevent_backend import CGEventInputBackend

CHAR_DELAY_S = 0.025
LOCK_WAIT_S = 0.50
LINE_SETTLE_S = 0.08


def sanitize_npc_name(npc_name: str) -> str:
    cleaned = "".join(ch for ch in str(npc_name) if ch.isprintable() and ch not in "\r\n\t")
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        raise ValueError("npc name is empty")
    return cleaned[:48]


def target_by_name(
    backend: CGEventInputBackend,
    npc_name: str,
    *,
    lock_probe: Callable[[], bool],
    sleeper: Callable[[float], None] = time.sleep,
    now_ns: Callable[[], int] | None = None,
    payload: dict[str, Any] | None = None,
    char_delay_s: float = CHAR_DELAY_S,
    lock_wait_s: float = LOCK_WAIT_S,
) -> bool:
    """Escape, Enter, /target Name, Enter. Escape again if the plate does not lock."""
    log = payload if payload is not None else {}
    clock = now_ns or mono_ns
    name = sanitize_npc_name(npc_name)
    command = f"/target {name}"
    log["chat_command"] = command
    if _tap_escape(backend, log) is None:
        return False
    sleeper(LINE_SETTLE_S)
    if _tap(backend, "return", log) is None:
        _tap_escape(backend, log)
        return False
    sleeper(LINE_SETTLE_S)
    typed = backend.type_text(command, sleeper=sleeper, delay_s=char_delay_s)
    log["hid_sent"] = bool(log.get("hid_sent") or typed.hid_sent)
    if not typed.accepted:
        log["aborted"] = typed.reason
        _tap_escape(backend, log)
        return False
    if _tap(backend, "return", log) is None:
        _tap_escape(backend, log)
        return False
    until = clock() + int(lock_wait_s * 1_000_000_000)
    while clock() < until:
        sleeper(0.05)
        try:
            if lock_probe():
                log["chat_target_success"] = True
                return True
        except Exception:
            continue
    try:
        if lock_probe():
            log["chat_target_success"] = True
            return True
    except Exception:
        pass
    _tap_escape(backend, log)
    log["chat_target_success"] = False
    return False


def _tap_escape(backend: CGEventInputBackend, payload: dict[str, Any]) -> Any | None:
    down = _send(backend, HoldKey(key="escape", duration_ms=40, state="down"), payload)
    if down is None:
        return None
    return _send(backend, HoldKey(key="escape", duration_ms=0, state="up"), payload)


def _tap(backend: CGEventInputBackend, key: str, payload: dict[str, Any]) -> Any | None:
    down = _send(backend, HoldKey(key=key, duration_ms=40, state="down"), payload)
    if down is None:
        return None
    return _send(backend, HoldKey(key=key, duration_ms=0, state="up"), payload)


def _send(backend: CGEventInputBackend, action: HoldKey, payload: dict[str, Any]) -> Any | None:
    event = backend.send_action(action)
    payload["hid_sent"] = bool(payload.get("hid_sent") or event.hid_sent)
    if event.reason == "kill_switch":
        payload["aborted"] = "kill_switch"
        return None
    if not event.accepted:
        payload["aborted"] = event.reason
        return None
    return event
