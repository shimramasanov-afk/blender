"""Live forward-flow probe. One continuous w hold. Not farm. Does not retune Frozen L1."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.bench.h8_latency_bench import summarize
from l2_brain.calibration.frame_sync import grab_shot, wait_unique_frame
from l2_brain.capture.errors import CaptureError
from l2_brain.capture.profile import WindowProfile
from l2_brain.contracts import Frame
from l2_brain.experiment.clocks import mono_ns
from l2_brain.io.actions import HoldKey
from l2_brain.io.cgevent_backend import CGEventInputBackend
from l2_brain.io.focus import frontmost_app, is_allowed_frontmost
from l2_brain.live.s4_probe import SCKGrabber, s4_input_profile
from l2_brain.vision.config import VisionConfig
from l2_brain.vision.encoder import NavigationEncoder
from l2_brain.vision.flow import FlowField

DEFAULT_PROFILE = Path("config/window_profiles/parallels_l2.json")
DEFAULT_OUT = Path("docs/evidence/live-s4/l1-flow-validation.json")
FREE_TICKS = 10
BLOCKED_TICKS = 3
HOLD_MS = 600
SETTLE_S = 0.30
MAX_SESSION_S = 40.0
RATIO_MIN = 3.0
FLOW_FREE_MIN = 0.25


def flow_magnitude_midnear(field: FlowField | None, near_y0: float = 0.45) -> float:
    """Mean |flow| on the lower/mid grid. Not Frozen L1."""
    if field is None or field.u.size == 0:
        return 0.0
    valid = (~field.weak_texture) & (field.confidence > 0.08)
    y_max = float(np.max(field.ys)) if field.ys.size else 1.0
    band = field.ys >= (near_y0 * y_max)
    use = valid & band
    if int(use.sum()) < 1:
        use = valid
    if int(use.sum()) < 1:
        return 0.0
    mag = np.hypot(field.u.astype(np.float32), field.v.astype(np.float32))
    return float(np.mean(mag[use]))


def _mean(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _as_frame(image: np.ndarray, frame_id: int, ts_ns: int) -> Frame:
    return Frame(
        frame_id=int(frame_id),
        timestamp_capture_ns=int(ts_ns),
        timestamp_received_ns=int(ts_ns),
        width=int(image.shape[1]),
        height=int(image.shape[0]),
        pixel_format="rgb8",
        source_id="sck.window",
        image=np.ascontiguousarray(image),
    )


def run_live_motion_probe(
    *,
    live: bool,
    danger_confirmed: bool,
    window_id: int | None = None,
    target_pid: int | None = None,
    profile_path: Path = DEFAULT_PROFILE,
    out_path: Path | None = DEFAULT_OUT,
    free_ticks: int = FREE_TICKS,
    blocked_ticks: int = BLOCKED_TICKS,
    hold_ms: int = HOLD_MS,
    grabber: Any | None = None,
    backend: CGEventInputBackend | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    now_ns: Callable[[], int] | None = None,
    focus_probe: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    clock = now_ns or mono_ns
    started = clock()
    payload: dict[str, Any] = {
        "ok": False,
        "live": bool(live and danger_confirmed),
        "aborted": None,
        "window_id": window_id,
        "target_pid": target_pid,
        "farm": False,
        "frozen_l1_untouched": True,
        "free_ticks": int(free_ticks),
        "blocked_ticks": int(blocked_ticks),
        "hold_ms": int(hold_ms),
        "hold_mode": "continuous",
        "stall_hypothesis": "H17",
        "ratio_min": RATIO_MIN,
        "flow_free_motion": None,
        "flow_blocked": None,
        "expansion_free": None,
        "expansion_blocked": None,
        "flow_ratio": None,
        "stuck_detected": False,
        "l1_collision_signal_ready": False,
        "encode": None,
        "ticks": [],
        "hid_sent": False,
        "stuck_keys_count": 0,
        "watchdog_tripped": False,
        "session_ms": 0.0,
        "steps": [],
        "events": [],
    }
    steps: list[dict[str, Any]] = payload["steps"]

    def add_step(name: str, **extra: Any) -> None:
        row = {"step": name, "t_ms": (clock() - started) / 1_000_000.0, **extra}
        steps.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    if not live or not danger_confirmed:
        payload["aborted"] = "live_flags_required"
        return _finish(payload, out_path, clock, started, None)
    if grabber is None and (window_id is None or int(window_id) < 1):
        payload["aborted"] = "window_id_required"
        return _finish(payload, out_path, clock, started, None)

    own_grabber = grabber is None
    own_backend = backend is None
    grabber = grabber or SCKGrabber(int(window_id or 0))
    if own_backend:
        pid = int(target_pid or 0)
        if pid < 1:
            info = frontmost_app()
            pid = int(info.pid) if info is not None else 0
        if pid < 1:
            payload["aborted"] = "no_target_pid"
            return _finish(payload, out_path, clock, started, None)
        payload["target_pid"] = pid
        backend = CGEventInputBackend(
            pid,
            live_confirmed=True,
            live_danger_confirmed=True,
            profile=s4_input_profile(),
            focus_probe=focus_probe or is_allowed_frontmost,
        )
    assert backend is not None
    focus = focus_probe or backend.check_window_focus
    profile = WindowProfile.load(profile_path) if profile_path.exists() else None
    encoder = NavigationEncoder(VisionConfig(profile=profile))
    encoder.initialize()
    encode_ms: list[float] = []
    frame_id = 0

    def expired() -> bool:
        return (clock() - started) / 1_000_000_000.0 >= MAX_SESSION_S

    def shot() -> tuple[np.ndarray, int] | None:
        if expired():
            payload["aborted"] = payload.get("aborted") or "session_timeout"
            return None
        if not focus():
            payload["aborted"] = "focus_lost"
            return None
        backend.pump()
        try:
            image, ts = grab_shot(grabber)
        except (CaptureError, RuntimeError):
            payload["aborted"] = "capture_lost"
            return None
        return image, ts

    def must_shot() -> tuple[np.ndarray, int]:
        got = shot()
        if got is None:
            raise RuntimeError("no frame")
        return got

    def beat() -> None:
        backend.watchdog.heartbeat(clock())
        backend.pump()

    walk_held = False

    def walk_down() -> bool:
        nonlocal walk_held
        if walk_held:
            return True
        down = backend.send_action(HoldKey(key="w", duration_ms=0, state="down"))
        payload["hid_sent"] = bool(payload.get("hid_sent") or getattr(down, "hid_sent", False))
        if getattr(down, "reason", None) == "kill_switch":
            payload["aborted"] = "kill_switch"
            add_step("abort", reason="kill_switch")
            return False
        if not getattr(down, "accepted", False):
            payload["aborted"] = getattr(down, "reason", "rejected")
            add_step("abort", reason=payload["aborted"])
            return False
        walk_held = True
        return True

    def walk_up() -> None:
        nonlocal walk_held
        if not walk_held:
            return
        backend.send_action(HoldKey(key="w", state="up"))
        backend.send_action(HoldKey(key="w", state="up"))
        walk_held = False

    def sample_tick(phase: str, index: int, ts0: int) -> tuple[dict[str, Any], int] | None:
        nonlocal frame_id
        try:
            t1, ts1, unique = wait_unique_frame(
                must_shot,
                ts0,
                int(hold_ms * 1_000_000),
                sleeper=sleeper,
                now_ns=clock,
                pump=beat,
                settle_s=0.05,
            )
        except (CaptureError, RuntimeError):
            add_step("abort", reason=payload.get("aborted") or "capture_lost", phase=phase)
            return None
        if payload.get("aborted"):
            add_step("abort", reason=payload.get("aborted"), phase=phase)
            return None
        frame_id += 1
        t_enc = time.perf_counter()
        obs = encoder.encode(_as_frame(t1, frame_id, ts1), (), None, clock(), False)
        enc_ms = (time.perf_counter() - t_enc) * 1000.0
        encode_ms.append(enc_ms)
        nav = obs.navigation
        mag = flow_magnitude_midnear(encoder.last_flow, encoder.config.near_y0)
        expansion = float(nav.expansion) if nav is not None else 0.0
        near_exp = float(nav.near.expansion) if nav is not None else 0.0
        motion_c = float(nav.motion_confidence) if nav is not None else 0.0
        row = {
            "phase": phase,
            "index": index,
            "flow_magnitude": mag,
            "expansion": expansion,
            "near_expansion": near_exp,
            "motion_confidence": motion_c,
            "encode_ms": enc_ms,
            "unique_frame": unique,
            "time_delta_ms": (ts1 - ts0) / 1_000_000.0,
            "duplicate": bool(nav.duplicate_frame) if nav is not None else False,
            "label": nav.hypothesis.label if nav is not None else None,
        }
        payload["ticks"].append(row)
        add_step("tick", **row)
        return row, ts1

    try:
        if not focus():
            payload["aborted"] = "focus_not_parallels"
            add_step("abort", reason="focus_not_parallels")
            return _finish(payload, out_path, clock, started, backend)
        grabber.start()
        hold_budget_ms = (max(int(free_ticks), 0) + max(int(blocked_ticks), 0)) * int(hold_ms)
        add_step(
            "capture_start",
            free_ticks=free_ticks,
            blocked_ticks=blocked_ticks,
            hold_ms=hold_ms,
            hold_mode="continuous",
            hold_budget_ms=hold_budget_ms,
            stall_risk=hold_budget_ms >= 4000,
        )
        if not walk_down():
            return _finish(payload, out_path, clock, started, backend)
        primed = shot()
        if primed is None:
            add_step("abort", reason=payload.get("aborted"))
            return _finish(payload, out_path, clock, started, backend)
        t0, ts_cursor = primed
        frame_id += 1
        encoder.encode(_as_frame(t0, frame_id, ts_cursor), (), None, clock(), False)
        for i in range(max(int(free_ticks), 0)):
            got = sample_tick("free", i, ts_cursor)
            if got is None:
                return _finish(payload, out_path, clock, started, backend)
            ts_cursor = got[1]
        for i in range(max(int(blocked_ticks), 0)):
            got = sample_tick("blocked", i, ts_cursor)
            if got is None:
                return _finish(payload, out_path, clock, started, backend)
            ts_cursor = got[1]
        walk_up()
        free_mags = [float(t["flow_magnitude"]) for t in payload["ticks"] if t["phase"] == "free"]
        block_mags = [float(t["flow_magnitude"]) for t in payload["ticks"] if t["phase"] == "blocked"]
        free_exp = [float(t["expansion"]) for t in payload["ticks"] if t["phase"] == "free"]
        block_exp = [float(t["expansion"]) for t in payload["ticks"] if t["phase"] == "blocked"]
        flow_free = _mean(free_mags)
        flow_block = _mean(block_mags)
        ratio = flow_free / flow_block if flow_block > 1e-9 else (float("inf") if flow_free > 1e-9 else 0.0)
        stuck = bool(flow_free >= FLOW_FREE_MIN and ratio >= RATIO_MIN)
        free_mc = [float(t["motion_confidence"]) for t in payload["ticks"] if t["phase"] == "free"]
        block_mc = [float(t["motion_confidence"]) for t in payload["ticks"] if t["phase"] == "blocked"]
        payload["flow_free_motion"] = flow_free
        payload["flow_blocked"] = flow_block
        payload["expansion_free"] = _mean(free_exp)
        payload["expansion_blocked"] = _mean(block_exp)
        payload["motion_confidence_free"] = _mean(free_mc)
        payload["motion_confidence_blocked"] = _mean(block_mc)
        payload["flow_ratio"] = ratio if ratio != float("inf") else None
        payload["flow_ratio_infinite"] = ratio == float("inf")
        payload["stuck_detected"] = stuck
        payload["l1_collision_signal_ready"] = stuck
        payload["encode"] = summarize(encode_ms)
        payload["ok"] = True
        add_step(
            "done",
            flow_free_motion=flow_free,
            flow_blocked=flow_block,
            flow_ratio=payload["flow_ratio"],
            stuck_detected=stuck,
        )
        return _finish(payload, out_path, clock, started, backend)
    except Exception as exc:  # noqa: BLE001 — always release HID and write a report
        payload["aborted"] = payload.get("aborted") or f"error:{type(exc).__name__}"
        add_step("abort", reason=payload["aborted"], error=str(exc)[:200])
        return _finish(payload, out_path, clock, started, backend)
    finally:
        encoder.close()
        if own_grabber:
            grabber.close()


def _finish(
    payload: dict[str, Any],
    out_path: Path | None,
    clock: Callable[[], int],
    started: int,
    backend: CGEventInputBackend | None,
) -> dict[str, Any]:
    if backend is not None:
        try:
            if payload.get("aborted") and payload["aborted"] not in ("live_flags_required", "no_target_pid"):
                from l2_brain.io.actions import EmergencyStop

                backend.send_action(EmergencyStop(reason=str(payload["aborted"])))
            backend.release_all()
        except Exception:  # noqa: BLE001 — probe must still write the report
            pass
        payload["stuck_keys_count"] = len(backend.watchdog.active_holds)
        payload["watchdog_tripped"] = bool(
            payload.get("watchdog_tripped") or any(row.reason == "watchdog_timeout" for row in backend.log)
        )
        payload["events"] = backend.events()
        payload["hid_sent"] = bool(payload.get("hid_sent") or any(row.hid_sent for row in backend.log))
    payload["session_ms"] = (clock() - started) / 1_000_000.0
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["out"] = str(out_path)
    return payload
