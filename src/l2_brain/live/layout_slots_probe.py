"""Live slot occupancy: Tab inventory, Escape clear. No farm. Not Frozen L1."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from l2_brain.capture.errors import CaptureError, SourceLost
from l2_brain.capture.helper import list_windows, resolve_helper
from l2_brain.experiment.clocks import mono_ns
from l2_brain.io.actions import HoldKey
from l2_brain.io.cgevent_backend import CGEventInputBackend
from l2_brain.io.focus import frontmost_app, is_allowed_frontmost
from l2_brain.live.s4_probe import SCKGrabber, TICK_S, _ms, s4_input_profile
from l2_brain.vision.layout_slots import DEFAULT_PROFILE, LayoutSlots
from l2_brain.vision.ui_manager import WindowManager

DEFAULT_OUT = Path("docs/evidence/live-s4/layout-slots-validation.json")


def run_layout_slots_probe(
    *,
    live: bool,
    danger_confirmed: bool,
    window_id: int | None = None,
    target_pid: int | None = None,
    profile_path: Path = DEFAULT_PROFILE,
    out_path: Path | None = DEFAULT_OUT,
    grabber: Any | None = None,
    backend: CGEventInputBackend | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    now_ns: Callable[[], int] | None = None,
    focus_probe: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    clock = now_ns or mono_ns
    started = clock()
    slots = LayoutSlots.load(profile_path)
    manager = WindowManager(slots)
    steps: list[dict[str, Any]] = []
    payload: dict[str, Any] = {
        "ok": False,
        "farm": False,
        "combat": False,
        "live": bool(live and danger_confirmed),
        "hid_sent": False,
        "aborted": None,
        "window_id": window_id,
        "target_pid": target_pid,
        "slot_a": list(slots.get("slot_dialog_left").window_px) if "slot_dialog_left" in slots.slots else None,
        "slot_b": list(slots.get("slot_modal_right").window_px) if "slot_modal_right" in slots.slots else None,
        "clean_free": None,
        "after_tab_occupied": None,
        "after_escape_free": None,
        "escapes_sent": 0,
        "tab_sent": False,
        "open_windows": [],
        "steps": steps,
        "events": [],
        "stuck_keys_count": 0,
        "watchdog_tripped": False,
    }
    if not live or not danger_confirmed:
        payload["aborted"] = "live_flags_required"
        return _finish(payload, out_path, clock, started, None)
    if grabber is None and (window_id is None or int(window_id) < 1):
        payload["aborted"] = "window_id_required"
        return _finish(payload, out_path, clock, started, None)

    own_grabber = grabber is None
    own_backend = backend is None
    grabber = grabber or SCKGrabber(int(window_id or 0), latest_timeout_s=4.0)
    if own_backend:
        pid = int(target_pid or 0)
        if pid < 1:
            info = frontmost_app()
            pid = int(info.pid) if info is not None else 0
        if pid < 1:
            payload["aborted"] = "no_target_pid"
            return _finish(payload, out_path, clock, started, None)
        payload["target_pid"] = pid
        origin = _window_origin(window_id)
        backend = CGEventInputBackend(
            pid,
            live_confirmed=True,
            live_danger_confirmed=True,
            profile=s4_input_profile(),
            focus_probe=focus_probe or is_allowed_frontmost,
            window_origin=origin,
        )
        size = _window_size(window_id)
        if size is not None:
            backend.window_size = size
    assert backend is not None
    focus = focus_probe or backend.check_window_focus

    def add_step(name: str, **extra: Any) -> None:
        row = {"step": name, "t_ms": _ms(clock(), started), **extra}
        steps.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    def sense() -> Any:
        if not focus():
            payload["aborted"] = "focus_lost"
            return None
        backend.pump()
        try:
            image = grabber.latest_image()
        except (CaptureError, RuntimeError) as exc:
            payload["aborted"] = "capture_lost"
            payload["capture_error"] = f"{type(exc).__name__}: {exc}"[:200]
            return None
        payload["_image"] = image
        return image

    def tap(key: str) -> bool:
        down = backend.send_action(HoldKey(key=key, duration_ms=40, state="down"))
        payload["hid_sent"] = bool(payload.get("hid_sent") or down.hid_sent)
        if not down.accepted:
            payload["aborted"] = down.reason
            return False
        up = backend.send_action(HoldKey(key=key, duration_ms=0, state="up"))
        return bool(up.accepted)

    try:
        if not focus():
            payload["aborted"] = "focus_not_parallels"
            add_step("abort", reason="focus_not_parallels")
            return _finish(payload, out_path, clock, started, backend)
        start_err: Exception | None = None
        for attempt in range(2):
            try:
                grabber.start()
                start_err = None
                break
            except (CaptureError, RuntimeError, SourceLost) as exc:
                start_err = exc
                grabber.close()
                sleeper(0.6)
        if start_err is not None:
            payload["aborted"] = "error:CaptureError"
            add_step("abort", reason="error:CaptureError", error=str(start_err)[:200])
            return _finish(payload, out_path, clock, started, backend)
        add_step("layout_start", farm=False)
        if sense() is None:
            add_step("abort", reason=payload.get("aborted"))
            return _finish(payload, out_path, clock, started, backend)
        occupied = manager.occupied_slots(payload["_image"])
        if occupied:
            add_step("pre_reset", occupied=occupied)
            manager.reset_ui(backend, sense, sleeper=sleeper, payload=payload)
            payload["escapes_sent"] = int(payload.get("escapes_sent") or 0) + 2
        if not tap("escape"):
            add_step("abort", reason=payload.get("aborted"))
            return _finish(payload, out_path, clock, started, backend)
        payload["escapes_sent"] = int(payload.get("escapes_sent") or 0) + 1
        sleeper(0.15)
        if sense() is None:
            add_step("abort", reason=payload.get("aborted"))
            return _finish(payload, out_path, clock, started, backend)
        payload["clean_free"] = not manager.is_slot_occupied("slot_modal_right", payload["_image"])
        add_step("clean", slot_b_occupied=not payload["clean_free"])
        if not tap("tab"):
            add_step("abort", reason=payload.get("aborted"))
            return _finish(payload, out_path, clock, started, backend)
        payload["tab_sent"] = True
        manager.open_modal("inventory")
        add_step("Tab", hid_sent=True)
        sleeper(0.40)
        if sense() is None:
            add_step("abort", reason=payload.get("aborted"))
            return _finish(payload, out_path, clock, started, backend)
        payload["after_tab_occupied"] = manager.is_slot_occupied("slot_modal_right", payload["_image"])
        add_step("after_tab", slot_b_occupied=payload["after_tab_occupied"])
        if not tap("escape"):
            add_step("abort", reason=payload.get("aborted"))
            return _finish(payload, out_path, clock, started, backend)
        payload["escapes_sent"] = int(payload.get("escapes_sent") or 0) + 1
        manager.close_active_modal()
        add_step("Escape", hid_sent=True)
        sleeper(0.15)
        if sense() is None:
            add_step("abort", reason=payload.get("aborted"))
            return _finish(payload, out_path, clock, started, backend)
        still = manager.is_slot_occupied("slot_modal_right", payload["_image"])
        if still:
            tap("escape")
            payload["escapes_sent"] = int(payload.get("escapes_sent") or 0) + 1
            sleeper(0.15)
            if sense() is None:
                add_step("abort", reason=payload.get("aborted"))
                return _finish(payload, out_path, clock, started, backend)
            still = manager.is_slot_occupied("slot_modal_right", payload["_image"])
        payload["after_escape_free"] = not still
        add_step("after_escape", slot_b_occupied=still)
        payload["open_windows"] = list(manager.open_windows)
        payload["ok"] = bool(payload["clean_free"] and payload["after_tab_occupied"] and payload["after_escape_free"])
        if not payload["ok"] and payload["clean_free"] and not payload["after_tab_occupied"]:
            payload["aborted"] = "inventory_not_in_slot_b"
        elif not payload["ok"] and not payload["after_escape_free"]:
            payload["aborted"] = "slot_b_still_occupied"
        add_step("SUCCESS" if payload["ok"] else "abort", reason=payload.get("aborted"))
        return _finish(payload, out_path, clock, started, backend)
    except Exception as exc:  # noqa: BLE001
        payload["aborted"] = payload.get("aborted") or f"error:{type(exc).__name__}"
        add_step("abort", reason=payload["aborted"], error=str(exc)[:200])
        return _finish(payload, out_path, clock, started, backend)
    finally:
        payload.pop("_image", None)
        if own_grabber:
            grabber.close()


def _window_origin(window_id: int | None) -> tuple[float, float]:
    row = _window_row(window_id)
    if row is None:
        return (0.0, 0.0)
    return (float(row.get("x") or 0.0), float(row.get("y") or 0.0))


def _window_size(window_id: int | None) -> tuple[float, float] | None:
    row = _window_row(window_id)
    if row is None:
        return None
    w, h = float(row.get("width") or 0), float(row.get("height") or 0)
    if w < 8 or h < 8:
        return None
    return (w, h)


def _window_row(window_id: int | None) -> dict[str, Any] | None:
    if window_id is None:
        return None
    try:
        data = list_windows(resolve_helper(build=False))
    except (OSError, RuntimeError, ValueError):
        return None
    for row in data.get("windows") or ():
        if int(row.get("id") or 0) == int(window_id):
            return dict(row)
    return None


def _finish(
    payload: dict[str, Any],
    out_path: Path | None,
    clock: Callable[[], int],
    started: int,
    backend: CGEventInputBackend | None,
) -> dict[str, Any]:
    from l2_brain.live.s4_probe import _finish as finish_probe

    payload.pop("_image", None)
    finished = finish_probe(payload, out_path, clock, started, backend)
    finished["elapsed_time_sec"] = float(finished.get("session_ms") or 0.0) / 1000.0
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(finished, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return finished
