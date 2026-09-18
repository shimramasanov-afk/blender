"""One-pulse yaw/walk pixel calibration. Not H8. FOV degrees are assumed."""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.calibration.frame_sync import (
    analysis_crop,
    grab_shot,
    pixel_diff_mean,
    wait_unique_frame,
    write_png,
)
from l2_brain.calibration.klt_yaw import (
    COARSE_PEAK_MIN,
    INLIER_COUNT_MIN,
    INLIER_RATIO_MIN,
    PIXEL_DIFF_MIN,
    SEARCH,
    WORK_X0,
    WORK_X1,
    WORK_Y0,
    WORK_Y1,
    coarse_shift,
    estimate_yaw_klt,
)
from l2_brain.capture.errors import CaptureError
from l2_brain.experiment.clocks import mono_ns
from l2_brain.io.cgevent_backend import CGEventInputBackend
from l2_brain.io.focus import frontmost_app, is_allowed_frontmost
from l2_brain.live.s4_probe import SEARCH_HOLD_MAX_MS, SCKGrabber, s4_input_profile
from l2_brain.vision.flow import scale_expansion
from l2_brain.vision.preprocess import to_gray

DEFAULT_PROFILE = Path("config/window_profiles/parallels_l2.json")
DEFAULT_OUT = Path("docs/evidence/live-s4/motion-calibration.json")
DEFAULT_OUT_V2 = Path("docs/evidence/live-s4/motion-calibration-v2.json")
DEFAULT_OUT_KLT = Path("docs/evidence/live-s4/motion-calibration-klt.json")
DEFAULT_OUT_V3 = Path("docs/evidence/live-s4/motion-calibration-v3.json")
DEFAULT_OUT_SYNC = Path("docs/evidence/live-s4/motion-sync-diag.json")
DEFAULT_DUMP_DIR = Path("run")
SYNC_MAX_SESSION_S = 16.0
SYNC_SETTLE_S = 0.30
SYNC_RMB_DX = 200
SYNC_HOLD_MS = 600
MAX_SESSION_S = 8.0
KLT_MAX_SESSION_S = 20.0
HOLD_MS = 500
KLT_HOLD_MS = 450
SYMMETRY_MAX_DEG_S = 1.5
SETTLE_S = 0.20
V3_SETTLE_S = 0.30
RMB_DX = 150
RMB_STEPS = 5
RMB_STEP_S = 0.01
ARROW_TAPS = 10
ARROW_INTERVAL_S = 0.04
PHYSICAL_DX_MIN = 30.0
PROFILE_DX_MIN = 50.0
CROP_W = 500
CROP_H = 300
HORIZON_Y0 = 0.15
HORIZON_Y1 = 0.30
HORIZON_X0 = 0.25
HORIZON_X1 = 0.75
PEAK_RELIABLE = 0.15
FOV_H_DEG_ASSUMED = 75.0
SHIFT_EPS_PX = 1.5


def center_crop(image: np.ndarray, width: int = CROP_W, height: int = CROP_H) -> np.ndarray:
    if image.ndim < 2:
        raise ValueError("image must be 2D or HxWxC")
    h, w = image.shape[:2]
    width = min(int(width), w)
    height = min(int(height), h)
    y0 = max(0, (h - height) // 2)
    x0 = max(0, (w - width) // 2)
    return np.ascontiguousarray(image[y0 : y0 + height, x0 : x0 + width])


def horizon_crop(
    image: np.ndarray,
    *,
    y0: float = HORIZON_Y0,
    y1: float = HORIZON_Y1,
    x0: float = HORIZON_X0,
    x1: float = HORIZON_X1,
) -> np.ndarray:
    """Sky / far horizon band. Character stays in the lower center, not here."""
    if image.ndim < 2:
        raise ValueError("image must be 2D or HxWxC")
    h, w = image.shape[:2]
    ya = min(h - 1, max(0, int(round(h * float(y0)))))
    yb = min(h, max(ya + 1, int(round(h * float(y1)))))
    xa = min(w - 1, max(0, int(round(w * float(x0)))))
    xb = min(w, max(xa + 1, int(round(w * float(x1)))))
    return np.ascontiguousarray(image[ya:yb, xa:xb])


def select_crop(image: np.ndarray, band: str = "horizon") -> np.ndarray:
    if band == "center":
        return center_crop(image)
    if band != "horizon":
        raise ValueError(f"unsupported crop band: {band}")
    return horizon_crop(image)


def phase_shift(prev: np.ndarray, curr: np.ndarray) -> tuple[float, float, float]:
    """Signed (dx, dy, peak). dx>0 means curr shifted right vs prev."""
    a = np.asarray(prev, dtype=np.float64)
    b = np.asarray(curr, dtype=np.float64)
    if a.ndim == 3:
        a = to_gray(a)
    if b.ndim == 3:
        b = to_gray(b)
    if a.shape != b.shape:
        raise ValueError("phase_shift frames must match")
    a = a - float(a.mean())
    b = b - float(b.mean())
    wy = np.hanning(a.shape[0])
    wx = np.hanning(a.shape[1])
    window = wy[:, None] * wx[None, :]
    fa = np.fft.fft2(a * window)
    fb = np.fft.fft2(b * window)
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-12
    corr = np.fft.fftshift(np.fft.ifft2(cross).real)
    peak = np.unravel_index(int(np.argmax(corr)), corr.shape)
    cy, cx = corr.shape[0] // 2, corr.shape[1] // 2
    dy = float(peak[0] - cy)
    dx = float(peak[1] - cx)
    py, px = int(peak[0]), int(peak[1])
    if 0 < py < corr.shape[0] - 1:
        ym = corr[py - 1, px]
        y0 = corr[py, px]
        yp = corr[py + 1, px]
        denom = ym - 2.0 * y0 + yp
        if abs(denom) > 1e-9:
            dy += 0.5 * (ym - yp) / denom
    if 0 < px < corr.shape[1] - 1:
        xm = corr[py, px - 1]
        x0 = corr[py, px]
        xp = corr[py, px + 1]
        denom = xm - 2.0 * x0 + xp
        if abs(denom) > 1e-9:
            dx += 0.5 * (xm - xp) / denom
    peak_val = float(corr[py, px])
    # Content motion in curr vs prev (np.roll +x → +dx), not the FFT peak sign.
    return -dx, -dy, peak_val


def yaw_deg_per_sec(shift_px: float, frame_width_px: int, hold_ms: int, fov_deg: float = FOV_H_DEG_ASSUMED) -> float:
    if frame_width_px < 1 or hold_ms < 1:
        return 0.0
    return float(shift_px) / float(frame_width_px) * float(fov_deg) / (hold_ms / 1000.0)


def turn_ms_for_deg(deg_per_sec: float, degrees: float) -> int | None:
    rate = abs(float(deg_per_sec))
    if rate < 1e-6:
        return None
    ms = int(round(abs(float(degrees)) / rate * 1000.0))
    if ms < 1 or ms > 20_000:
        return None
    return ms


def motion_block(
    *,
    yaw_shift_px: float,
    deg_per_sec: float,
    step_px_per_sec: float,
    turn_90_ms: int | None,
    yaw_peak: float = 0.0,
    step_peak: float = 0.0,
    band: str = "center",
    h8_closed: bool = False,
) -> dict[str, Any]:
    reliable = float(yaw_peak) >= PEAK_RELIABLE
    if band == "horizon":
        confidence = "ok" if reliable else "unreliable"
    else:
        peak_ok = float(yaw_peak) >= 0.08 or float(step_peak) >= 0.08
        confidence = "ok" if peak_ok else "low"
    return {
        "rotation_backend": "keyboard_arrow",
        "arrow_right_keycode": 124,
        "arrow_left_keycode": 123,
        "yaw_rate_deg_per_sec": deg_per_sec,
        "step_px_per_sec": step_px_per_sec,
        "turn_90_duration_ms": turn_90_ms,
        "fov_h_deg_assumed": FOV_H_DEG_ASSUMED,
        "yaw_from_assumed_fov": True,
        "hold_ms": HOLD_MS,
        "yaw_shift_px": yaw_shift_px,
        "yaw_peak": yaw_peak,
        "step_peak": step_peak,
        "crop_band": band,
        "crop_y": [HORIZON_Y0, HORIZON_Y1] if band == "horizon" else None,
        "crop_x": [HORIZON_X0, HORIZON_X1] if band == "horizon" else None,
        "peak_threshold": PEAK_RELIABLE,
        "peak_reliable": reliable,
        "confidence": confidence,
        "h8_closed": bool(h8_closed),
        "q5_gt_yaw": False,
    }


def write_profile_motion(profile_path: Path, block: dict[str, Any]) -> None:
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    data["motion"] = block
    profile_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_motion_calibration(
    *,
    live: bool,
    danger_confirmed: bool,
    window_id: int | None = None,
    target_pid: int | None = None,
    profile_path: Path = DEFAULT_PROFILE,
    out_path: Path | None = DEFAULT_OUT,
    write_profile: bool = False,
    band: str = "center",
    skip_walk: bool | None = None,
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
        "rotation_type": "keyboard_arrow",
        "yaw_shift_px": None,
        "yaw_shift_dy_px": None,
        "yaw_peak": None,
        "deg_per_sec": None,
        "step_shift_px": None,
        "step_shift_dx_px": None,
        "step_shift_dy_px": None,
        "step_scale": None,
        "step_peak": None,
        "step_px_per_sec": None,
        "motion_detected": False,
        "fov_h_deg_assumed": FOV_H_DEG_ASSUMED,
        "yaw_from_assumed_fov": True,
        "h8_closed": False,
        "q5_gt_yaw": False,
        "hid_sent": False,
        "stuck_keys_count": 0,
        "watchdog_tripped": False,
        "ticks": 0,
        "session_ms": 0.0,
        "steps": [],
        "events": [],
        "farm": False,
        "transfer_claim": False,
        "crop_band": band,
        "crop_y": [HORIZON_Y0, HORIZON_Y1] if band == "horizon" else None,
        "crop_x": [HORIZON_X0, HORIZON_X1] if band == "horizon" else None,
        "peak_threshold": PEAK_RELIABLE,
        "peak_reliable": False,
        "q5_horizon_ok": False,
        "q5_closed": False,
    }
    do_walk = (not bool(skip_walk)) if skip_walk is not None else band != "horizon"
    steps: list[dict[str, Any]] = payload["steps"]

    def add_step(name: str, **extra: Any) -> None:
        row = {"step": name, "t_ms": (clock() - started) / 1_000_000.0, **extra}
        steps.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    if not live or not danger_confirmed:
        payload["aborted"] = "live_flags_required"
        return _finish(payload, out_path, clock, started, None, write_profile=False, profile_path=profile_path)
    if grabber is None and (window_id is None or int(window_id) < 1):
        payload["aborted"] = "window_id_required"
        return _finish(payload, out_path, clock, started, None, write_profile=False, profile_path=profile_path)

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
            return _finish(payload, out_path, clock, started, None, write_profile=False, profile_path=profile_path)
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

    def expired() -> bool:
        return (clock() - started) / 1_000_000_000.0 >= MAX_SESSION_S

    def grab() -> np.ndarray | None:
        if expired():
            payload["aborted"] = payload.get("aborted") or "session_timeout"
            return None
        if not focus():
            payload["aborted"] = "focus_lost"
            return None
        backend.pump()
        try:
            image = grabber.latest_image()
        except (CaptureError, RuntimeError):
            payload["aborted"] = "capture_lost"
            return None
        payload["ticks"] = int(payload["ticks"]) + 1
        return image

    def hold(key: str) -> bool:
        ev = backend.hold_key_timed(key, HOLD_MS, sleeper=sleeper)
        payload["hid_sent"] = bool(payload.get("hid_sent") or ev.hid_sent)
        if ev.reason == "kill_switch":
            payload["aborted"] = "kill_switch"
            return False
        if not ev.accepted:
            payload["aborted"] = ev.reason
            return False
        return True

    try:
        if not focus():
            payload["aborted"] = "focus_not_parallels"
            add_step("abort", reason="focus_not_parallels")
            return _finish(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        grabber.start()
        add_step(
            "capture_start",
            crop_band=band,
            crop=[CROP_W, CROP_H] if band == "center" else None,
            crop_y=[HORIZON_Y0, HORIZON_Y1] if band == "horizon" else None,
            crop_x=[HORIZON_X0, HORIZON_X1] if band == "horizon" else None,
            hold_ms=HOLD_MS,
            fov_h_deg_assumed=FOV_H_DEG_ASSUMED,
        )
        frame0 = grab()
        if frame0 is None:
            add_step("abort", reason=payload.get("aborted"))
            return _finish(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        crop0 = select_crop(frame0, band)
        add_step("I0", shape=list(crop0.shape[:2]), frame_w=int(frame0.shape[1]), crop_band=band)
        if not hold("right_arrow"):
            add_step("abort", reason=payload.get("aborted"))
            return _finish(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        add_step("right_arrow", duration_ms=HOLD_MS)
        sleeper(SETTLE_S)
        frame1 = grab()
        if frame1 is None:
            add_step("abort", reason=payload.get("aborted"))
            return _finish(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        crop1 = select_crop(frame1, band)
        dx, dy, peak = phase_shift(crop0, crop1)
        hold_s = HOLD_MS / 1000.0
        deg = yaw_deg_per_sec(dx, int(frame0.shape[1]), HOLD_MS)
        payload["yaw_shift_px"] = dx
        payload["yaw_shift_dy_px"] = dy
        payload["yaw_peak"] = peak
        payload["deg_per_sec"] = deg
        payload["peak_reliable"] = float(peak) >= PEAK_RELIABLE
        payload["q5_horizon_ok"] = bool(band == "horizon" and payload["peak_reliable"])
        add_step("I1", yaw_shift_px=dx, yaw_shift_dy_px=dy, peak=peak, deg_per_sec=deg, peak_reliable=payload["peak_reliable"])

        step_mag = 0.0
        scale = 1.0
        if do_walk:
            crop2 = crop1
            add_step("I2")
            if not hold("w"):
                add_step("abort", reason=payload.get("aborted"))
                return _finish(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
            add_step("HoldKey", key="w", duration_ms=HOLD_MS)
            sleeper(SETTLE_S)
            frame3 = grab()
            if frame3 is None:
                add_step("abort", reason=payload.get("aborted"))
                return _finish(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
            crop3 = select_crop(frame3, band)
            sdx, sdy, speak = phase_shift(crop2, crop3)
            scale_delta, scale_conf = scale_expansion(to_gray(crop2), to_gray(crop3))
            scale = 1.0 + float(scale_delta)
            step_mag = float(np.hypot(sdx, sdy))
            payload["step_shift_px"] = step_mag
            payload["step_shift_dx_px"] = sdx
            payload["step_shift_dy_px"] = sdy
            payload["step_scale"] = scale
            payload["step_peak"] = speak
            payload["step_px_per_sec"] = step_mag / hold_s
            add_step(
                "I3",
                step_shift_px=step_mag,
                step_dx=sdx,
                step_dy=sdy,
                step_peak=speak,
                step_scale=scale,
                step_scale_conf=scale_conf,
                step_px_per_sec=payload["step_px_per_sec"],
            )
        payload["motion_detected"] = bool(
            abs(dx) >= SHIFT_EPS_PX or step_mag >= SHIFT_EPS_PX or abs(float(scale) - 1.0) >= 0.02
        )
        payload["ok"] = True
        add_step("done", motion_detected=payload["motion_detected"], peak_reliable=payload["peak_reliable"])
        allow_write = bool(write_profile)
        if band == "horizon":
            allow_write = allow_write and bool(payload["peak_reliable"])
        else:
            allow_write = allow_write and bool(payload["motion_detected"])
        return _finish(
            payload,
            out_path,
            clock,
            started,
            backend,
            write_profile=allow_write,
            profile_path=profile_path,
        )
    except Exception as exc:  # noqa: BLE001 — always release HID and write a report
        payload["aborted"] = payload.get("aborted") or f"error:{type(exc).__name__}"
        add_step("abort", reason=payload["aborted"], error=str(exc)[:200])
        return _finish(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
    finally:
        if own_grabber:
            grabber.close()


def _finish(
    payload: dict[str, Any],
    out_path: Path | None,
    clock: Callable[[], int],
    started: int,
    backend: CGEventInputBackend | None,
    *,
    write_profile: bool,
    profile_path: Path,
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
            payload.get("watchdog_tripped")
            or any(row.reason == "watchdog_timeout" for row in backend.log)
        )
        payload["events"] = backend.events()
        payload["hid_sent"] = bool(payload.get("hid_sent") or any(row.hid_sent for row in backend.log))
    payload["session_ms"] = (clock() - started) / 1_000_000.0
    if payload.get("ok") and payload.get("yaw_peak") is not None:
        turn90 = turn_ms_for_deg(float(payload.get("deg_per_sec") or 0.0), 90.0)
        payload["motion"] = motion_block(
            yaw_shift_px=float(payload.get("yaw_shift_px") or 0.0),
            deg_per_sec=float(payload.get("deg_per_sec") or 0.0),
            step_px_per_sec=float(payload.get("step_px_per_sec") or 0.0),
            turn_90_ms=turn90,
            yaw_peak=float(payload.get("yaw_peak") or 0.0),
            step_peak=float(payload.get("step_peak") or 0.0),
            band=str(payload.get("crop_band") or "center"),
        )
        if write_profile and profile_path.exists():
            write_profile_motion(profile_path, payload["motion"])
            payload["profile_written"] = str(profile_path)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["out"] = str(out_path)
    return payload


def klt_motion_block(
    *,
    right: dict[str, Any],
    left: dict[str, Any],
    deg_right: float,
    deg_left: float,
    reliable: bool,
    symmetry_ok: bool,
    hold_ms: int = KLT_HOLD_MS,
) -> dict[str, Any]:
    rate = 0.5 * (abs(float(deg_right)) + abs(float(deg_left)))
    signed = float(deg_right)
    turn90 = turn_ms_for_deg(rate, 90.0)
    return {
        "rotation_backend": "keyboard_arrow",
        "algorithm": "klt_ransac",
        "arrow_right_keycode": 124,
        "arrow_left_keycode": 123,
        "camera_deg_per_sec": rate,
        "yaw_rate_deg_per_sec": signed,
        "yaw_rate_deg_per_sec_right": float(deg_right),
        "yaw_rate_deg_per_sec_left": float(deg_left),
        "step_px_per_sec": None,
        "turn_90_duration_ms": turn90,
        "fov_h_deg_assumed": FOV_H_DEG_ASSUMED,
        "yaw_from_assumed_fov": True,
        "hold_ms": int(hold_ms),
        "yaw_shift_px": right.get("median_dx"),
        "right": right,
        "left": left,
        "inlier_ratio_min": INLIER_RATIO_MIN,
        "inlier_count_min": INLIER_COUNT_MIN,
        "symmetry_max_deg_s": SYMMETRY_MAX_DEG_S,
        "symmetry_ok": bool(symmetry_ok),
        "reliable": bool(reliable),
        "confidence": "ok" if reliable else "unreliable",
        "h8_closed": True,
        "q5_gt_yaw": False,
        "q5_closed": bool(reliable),
    }


def run_klt_yaw_calibration(
    *,
    live: bool,
    danger_confirmed: bool,
    window_id: int | None = None,
    target_pid: int | None = None,
    profile_path: Path = DEFAULT_PROFILE,
    out_path: Path | None = DEFAULT_OUT_KLT,
    write_profile: bool = False,
    grabber: Any | None = None,
    backend: CGEventInputBackend | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    now_ns: Callable[[], int] | None = None,
    focus_probe: Callable[[], bool] | None = None,
    hold_ms: int = KLT_HOLD_MS,
) -> dict[str, Any]:
    clock = now_ns or mono_ns
    started = clock()
    hold_ms = min(max(int(hold_ms), 1), SEARCH_HOLD_MAX_MS)
    payload: dict[str, Any] = {
        "ok": False,
        "live": bool(live and danger_confirmed),
        "aborted": None,
        "window_id": window_id,
        "target_pid": target_pid,
        "rotation_type": "keyboard_arrow",
        "algorithm": "klt_ransac",
        "hold_ms": hold_ms,
        "fov_h_deg_assumed": FOV_H_DEG_ASSUMED,
        "yaw_from_assumed_fov": True,
        "right": None,
        "left": None,
        "median_dx": None,
        "deg_per_sec": None,
        "deg_per_sec_right": None,
        "deg_per_sec_left": None,
        "symmetry_abs_deg_s": None,
        "symmetry_ok": False,
        "reliable": False,
        "q5_closed": False,
        "q5_gt_yaw": False,
        "h8_closed": True,
        "hid_sent": False,
        "stuck_keys_count": 0,
        "watchdog_tripped": False,
        "ticks": 0,
        "session_ms": 0.0,
        "steps": [],
        "events": [],
        "farm": False,
        "profile_written": None,
    }
    steps: list[dict[str, Any]] = payload["steps"]

    def add_step(name: str, **extra: Any) -> None:
        row = {"step": name, "t_ms": (clock() - started) / 1_000_000.0, **extra}
        steps.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    if not live or not danger_confirmed:
        payload["aborted"] = "live_flags_required"
        return _finish_klt(payload, out_path, clock, started, None, write_profile=False, profile_path=profile_path)
    if grabber is None and (window_id is None or int(window_id) < 1):
        payload["aborted"] = "window_id_required"
        return _finish_klt(payload, out_path, clock, started, None, write_profile=False, profile_path=profile_path)

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
            return _finish_klt(payload, out_path, clock, started, None, write_profile=False, profile_path=profile_path)
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

    def expired() -> bool:
        return (clock() - started) / 1_000_000_000.0 >= KLT_MAX_SESSION_S

    def grab() -> np.ndarray | None:
        if expired():
            payload["aborted"] = payload.get("aborted") or "session_timeout"
            return None
        if not focus():
            payload["aborted"] = "focus_lost"
            return None
        backend.pump()
        try:
            image = grabber.latest_image()
        except (CaptureError, RuntimeError):
            payload["aborted"] = "capture_lost"
            return None
        payload["ticks"] = int(payload["ticks"]) + 1
        return image

    def hold(key: str) -> bool:
        ev = backend.hold_key_timed(key, hold_ms, sleeper=sleeper)
        payload["hid_sent"] = bool(payload.get("hid_sent") or ev.hid_sent)
        if ev.reason == "kill_switch":
            payload["aborted"] = "kill_switch"
            return False
        if not ev.accepted:
            payload["aborted"] = ev.reason
            return False
        return True

    def pulse(key: str, before: np.ndarray) -> tuple[np.ndarray | None, dict[str, Any] | None]:
        if not hold(key):
            add_step("abort", reason=payload.get("aborted"), key=key)
            return None, None
        add_step(key, duration_ms=hold_ms)
        sleeper(SETTLE_S)
        after = grab()
        if after is None:
            add_step("abort", reason=payload.get("aborted"), key=key)
            return None, None
        est = estimate_yaw_klt(before, after, profile_path=profile_path)
        deg = yaw_deg_per_sec(est.median_dx, int(before.shape[1]), hold_ms)
        row = {**est.to_dict(), "deg_per_sec": deg, "frame_w": int(before.shape[1])}
        add_step("klt", key=key, **row)
        return after, row

    try:
        if not focus():
            payload["aborted"] = "focus_not_parallels"
            add_step("abort", reason="focus_not_parallels")
            return _finish_klt(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        grabber.start()
        add_step(
            "capture_start",
            algorithm="klt_ransac",
            work_y=[WORK_Y0, WORK_Y1],
            work_x=[WORK_X0, WORK_X1],
            hold_ms=hold_ms,
            fov_h_deg_assumed=FOV_H_DEG_ASSUMED,
        )
        frame0 = grab()
        if frame0 is None:
            add_step("abort", reason=payload.get("aborted"))
            return _finish_klt(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        add_step("I0", shape=list(frame0.shape[:2]))
        frame1, right = pulse("right_arrow", frame0)
        if frame1 is None or right is None:
            return _finish_klt(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        payload["right"] = right
        frame2, left = pulse("left_arrow", frame1)
        if frame2 is None or left is None:
            return _finish_klt(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        payload["left"] = left
        deg_r = float(right["deg_per_sec"])
        deg_l = float(left["deg_per_sec"])
        sym = abs(deg_r + deg_l)
        both = bool(right["reliable"] and left["reliable"])
        symmetry_ok = bool(sym <= SYMMETRY_MAX_DEG_S)
        reliable = bool(both and symmetry_ok)
        payload["median_dx"] = right["median_dx"]
        payload["deg_per_sec"] = deg_r
        payload["deg_per_sec_right"] = deg_r
        payload["deg_per_sec_left"] = deg_l
        payload["symmetry_abs_deg_s"] = sym
        payload["symmetry_ok"] = symmetry_ok
        payload["reliable"] = reliable
        payload["q5_closed"] = reliable
        payload["ok"] = True
        add_step(
            "done",
            reliable=reliable,
            symmetry_ok=symmetry_ok,
            symmetry_abs_deg_s=sym,
            q5_closed=reliable,
        )
        return _finish_klt(
            payload,
            out_path,
            clock,
            started,
            backend,
            write_profile=bool(write_profile and reliable),
            profile_path=profile_path,
        )
    except Exception as exc:  # noqa: BLE001 — always release HID and write a report
        payload["aborted"] = payload.get("aborted") or f"error:{type(exc).__name__}"
        add_step("abort", reason=payload["aborted"], error=str(exc)[:200])
        return _finish_klt(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
    finally:
        if own_grabber:
            grabber.close()


def _finish_klt(
    payload: dict[str, Any],
    out_path: Path | None,
    clock: Callable[[], int],
    started: int,
    backend: CGEventInputBackend | None,
    *,
    write_profile: bool,
    profile_path: Path,
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
            payload.get("watchdog_tripped")
            or any(row.reason == "watchdog_timeout" for row in backend.log)
        )
        payload["events"] = backend.events()
        payload["hid_sent"] = bool(payload.get("hid_sent") or any(row.hid_sent for row in backend.log))
    payload["session_ms"] = (clock() - started) / 1_000_000.0
    if payload.get("ok") and payload.get("right") is not None and payload.get("left") is not None:
        payload["motion"] = klt_motion_block(
            right=dict(payload["right"]),
            left=dict(payload["left"]),
            deg_right=float(payload.get("deg_per_sec_right") or 0.0),
            deg_left=float(payload.get("deg_per_sec_left") or 0.0),
            reliable=bool(payload.get("reliable")),
            symmetry_ok=bool(payload.get("symmetry_ok")),
            hold_ms=int(payload.get("hold_ms") or KLT_HOLD_MS),
        )
        if write_profile and bool(payload.get("reliable")) and profile_path.exists():
            write_profile_motion(profile_path, payload["motion"])
            payload["profile_written"] = str(profile_path)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["out"] = str(out_path)
    return payload


def attach_window_geometry(backend: CGEventInputBackend, window_id: int | None) -> dict[str, Any] | None:
    if window_id is None or int(window_id) < 1:
        return None
    from l2_brain.capture.helper import list_windows, resolve_helper

    try:
        data = list_windows(resolve_helper(build=False))
    except Exception:  # noqa: BLE001 — geometry is optional for scripted tests
        return None
    for row in data.get("windows") or ():
        if int(row.get("id") or 0) != int(window_id):
            continue
        backend.window_origin = (float(row.get("x") or 0.0), float(row.get("y") or 0.0))
        backend.window_size = (float(row.get("width") or 0.0), float(row.get("height") or 0.0))
        return {
            "window_id": int(window_id),
            "x": backend.window_origin[0],
            "y": backend.window_origin[1],
            "width": backend.window_size[0],
            "height": backend.window_size[1],
            "on_screen": bool(row.get("on_screen")),
        }
    return None


def v3_motion_block(
    *,
    mechanism: str,
    klt: dict[str, Any],
    mouse_dx: float,
    frame_width: int,
) -> dict[str, Any]:
    median_dx = float(klt.get("median_dx") or 0.0)
    coarse_dx = float(klt.get("coarse_dx") or 0.0)
    px_cam = float(median_dx) / float(mouse_dx) if abs(float(mouse_dx)) >= 1 else 0.0
    deg_mouse = (px_cam / float(frame_width)) * FOV_H_DEG_ASSUMED if frame_width >= 1 else 0.0
    klt_ok = bool(klt.get("reliable"))
    klt_physical = klt_ok and abs(median_dx) >= PHYSICAL_DX_MIN
    coarse_physical = bool(klt.get("coarse_physical")) or (
        abs(coarse_dx) >= PHYSICAL_DX_MIN and float(klt.get("coarse_peak") or 0.0) >= COARSE_PEAK_MIN
    ) or float(klt.get("pixel_diff_mean") or 0.0) >= PIXEL_DIFF_MIN
    camera_moved = klt_physical or coarse_physical
    profile_ok = klt_ok and abs(median_dx) >= PROFILE_DX_MIN
    assumed_yaw_deg = (coarse_dx / float(frame_width)) * FOV_H_DEG_ASSUMED if frame_width >= 1 else 0.0
    return {
        "rotation_backend": mechanism,
        "algorithm": "klt_ransac+coarse_phase",
        "camera_deg_per_sec": None,
        "px_cam_per_px_mouse": px_cam,
        "deg_per_mouse_px": deg_mouse,
        "mouse_dx_px": float(mouse_dx),
        "yaw_shift_px": median_dx,
        "coarse_dx": coarse_dx,
        "coarse_peak": float(klt.get("coarse_peak") or 0.0),
        "pixel_diff_mean": float(klt.get("pixel_diff_mean") or 0.0),
        "klt_search_px": int(klt.get("klt_search_px") or SEARCH),
        "assumed_yaw_deg": assumed_yaw_deg,
        "fov_h_deg_assumed": FOV_H_DEG_ASSUMED,
        "yaw_from_assumed_fov": True,
        "klt": klt,
        "physical_dx_min": PHYSICAL_DX_MIN,
        "profile_dx_min": PROFILE_DX_MIN,
        "physical": camera_moved,
        "klt_physical": klt_physical,
        "coarse_physical": coarse_physical,
        "reliable": profile_ok,
        "confidence": "ok" if profile_ok else "unreliable",
        "h8_closed": True,
        "q5_gt_yaw": False,
        "q5_closed": klt_physical,
    }


def run_v3_yaw_calibration(
    *,
    live: bool,
    danger_confirmed: bool,
    window_id: int | None = None,
    target_pid: int | None = None,
    profile_path: Path = DEFAULT_PROFILE,
    out_path: Path | None = DEFAULT_OUT_V3,
    write_profile: bool = False,
    grabber: Any | None = None,
    backend: CGEventInputBackend | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    now_ns: Callable[[], int] | None = None,
    focus_probe: Callable[[], bool] | None = None,
    mouse_dx: float = RMB_DX,
    mouse_dy: float = 0.0,
    rmb_steps: int = RMB_STEPS,
    rmb_step_s: float = RMB_STEP_S,
    arrow_taps: int = ARROW_TAPS,
    arrow_hold_ms: int = 0,
) -> dict[str, Any]:
    clock = now_ns or mono_ns
    started = clock()
    payload: dict[str, Any] = {
        "ok": False,
        "live": bool(live and danger_confirmed),
        "aborted": None,
        "window_id": window_id,
        "target_pid": target_pid,
        "algorithm": "klt_ransac",
        "attempts": [],
        "mechanism": None,
        "median_dx": None,
        "total_features": None,
        "valid_inliers": None,
        "inlier_ratio": None,
        "px_cam_per_px_mouse": None,
        "deg_per_mouse_px": None,
        "physical": False,
        "reliable": False,
        "q5_closed": False,
        "q5_gt_yaw": False,
        "h8_closed": True,
        "hid_sent": False,
        "stuck_keys_count": 0,
        "watchdog_tripped": False,
        "ticks": 0,
        "session_ms": 0.0,
        "steps": [],
        "events": [],
        "farm": False,
        "profile_written": None,
        "window": None,
    }
    steps: list[dict[str, Any]] = payload["steps"]

    def add_step(name: str, **extra: Any) -> None:
        row = {"step": name, "t_ms": (clock() - started) / 1_000_000.0, **extra}
        steps.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    if not live or not danger_confirmed:
        payload["aborted"] = "live_flags_required"
        return _finish_v3(payload, out_path, clock, started, None, write_profile=False, profile_path=profile_path)
    if grabber is None and (window_id is None or int(window_id) < 1):
        payload["aborted"] = "window_id_required"
        return _finish_v3(payload, out_path, clock, started, None, write_profile=False, profile_path=profile_path)

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
            return _finish_v3(payload, out_path, clock, started, None, write_profile=False, profile_path=profile_path)
        payload["target_pid"] = pid
        backend = CGEventInputBackend(
            pid,
            live_confirmed=True,
            live_danger_confirmed=True,
            profile=s4_input_profile(),
            focus_probe=focus_probe or is_allowed_frontmost,
        )
    assert backend is not None
    payload["window"] = attach_window_geometry(backend, window_id)
    focus = focus_probe or backend.check_window_focus

    def expired() -> bool:
        return (clock() - started) / 1_000_000_000.0 >= KLT_MAX_SESSION_S

    def grab() -> np.ndarray | None:
        if expired():
            payload["aborted"] = payload.get("aborted") or "session_timeout"
            return None
        if not focus():
            payload["aborted"] = "focus_lost"
            return None
        backend.pump()
        try:
            image = grabber.latest_image()
        except (CaptureError, RuntimeError):
            payload["aborted"] = "capture_lost"
            return None
        payload["ticks"] = int(payload["ticks"]) + 1
        return np.ascontiguousarray(image).copy()

    def measure(name: str, fire: Callable[[], Any]) -> dict[str, Any] | None:
        before = grab()
        if before is None:
            add_step("abort", reason=payload.get("aborted"), attempt=name)
            return None
        ev = fire()
        payload["hid_sent"] = bool(payload.get("hid_sent") or getattr(ev, "hid_sent", False))
        if getattr(ev, "reason", None) == "kill_switch":
            payload["aborted"] = "kill_switch"
            add_step("abort", reason="kill_switch", attempt=name)
            return None
        if not getattr(ev, "accepted", False):
            payload["aborted"] = getattr(ev, "reason", "rejected")
            add_step("abort", reason=payload["aborted"], attempt=name)
            return None
        add_step(name, accepted=True, reason=getattr(ev, "reason", None))
        sleeper(V3_SETTLE_S)
        flushed = grab()
        if flushed is None:
            add_step("abort", reason=payload.get("aborted"), attempt=name)
            return None
        after = grab()
        if after is None:
            add_step("abort", reason=payload.get("aborted"), attempt=name)
            return None
        est = estimate_yaw_klt(before, after, profile_path=profile_path)
        coarse = coarse_shift(before, after, profile_path=profile_path)
        klt_phys = bool(est.reliable and abs(est.median_dx) >= PHYSICAL_DX_MIN)
        coarse_phys = bool(
            (
                abs(float(coarse["coarse_dx"])) >= PHYSICAL_DX_MIN
                and float(coarse["coarse_peak"]) >= COARSE_PEAK_MIN
            )
            or float(coarse["pixel_diff_mean"]) >= PIXEL_DIFF_MIN
        )
        t0_png = t1_png = None
        if out_path is not None:
            dump_dir = Path(out_path).parent
            t0_png = dump_dir / f"yaw-{name}-t0.png"
            t1_png = dump_dir / f"yaw-{name}-t1.png"
            write_png(t0_png, before)
            write_png(t1_png, after)
        row = {
            **est.to_dict(),
            **coarse,
            "mechanism": name,
            "frame_w": int(before.shape[1]),
            "klt_search_px": SEARCH,
            "physical": klt_phys or coarse_phys,
            "klt_physical": klt_phys,
            "coarse_physical": coarse_phys,
            "t0_png": str(t0_png) if t0_png is not None else None,
            "t1_png": str(t1_png) if t1_png is not None else None,
        }
        payload["attempts"].append(row)
        add_step("klt", **row)
        return row

    try:
        if not focus():
            payload["aborted"] = "focus_not_parallels"
            add_step("abort", reason="focus_not_parallels")
            return _finish_v3(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        grabber.start()
        add_step(
            "capture_start",
            work_y=[WORK_Y0, WORK_Y1],
            work_x=[WORK_X0, WORK_X1],
            mouse_dx=mouse_dx,
            mouse_dy=float(mouse_dy),
            rmb_steps=int(rmb_steps),
            rmb_step_s=float(rmb_step_s),
            arrow_taps=int(arrow_taps),
            arrow_hold_ms=int(arrow_hold_ms),
            fov_h_deg_assumed=FOV_H_DEG_ASSUMED,
        )
        rmb = measure(
            "rmb_drag",
            lambda: backend.rmb_drag(
                mouse_dx,
                dy_pixels=float(mouse_dy),
                steps=max(int(rmb_steps), 1),
                step_delay_s=float(rmb_step_s),
                sleeper=sleeper,
            ),
        )
        if payload.get("aborted"):
            return _finish_v3(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        chosen = rmb if rmb and rmb.get("physical") else None
        if chosen is None:
            pulse = measure(
                "arrow_pulse",
                lambda: backend.arrow_pulse(
                    "right_arrow",
                    taps=max(int(arrow_taps), 1),
                    interval_s=ARROW_INTERVAL_S,
                    sleeper=sleeper,
                ),
            )
            if payload.get("aborted"):
                return _finish_v3(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
            if pulse and pulse.get("physical"):
                chosen = pulse
        if chosen is None and int(arrow_hold_ms) > 0:
            hold_ms = int(arrow_hold_ms)
            hold = measure(
                "arrow_hold",
                lambda: backend.hold_key_timed(
                    "right_arrow",
                    hold_ms,
                    sleeper=sleeper,
                    cap_ms=hold_ms,
                ),
            )
            if payload.get("aborted"):
                return _finish_v3(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
            if hold and hold.get("physical"):
                chosen = hold
        if chosen is None:
            chosen = rmb or (payload["attempts"][-1] if payload["attempts"] else None)
        if chosen is None:
            payload["aborted"] = payload.get("aborted") or "no_measurement"
            return _finish_v3(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        payload["mechanism"] = chosen.get("mechanism")
        payload["median_dx"] = chosen.get("median_dx")
        payload["coarse_dx"] = chosen.get("coarse_dx")
        payload["coarse_peak"] = chosen.get("coarse_peak")
        payload["pixel_diff_mean"] = chosen.get("pixel_diff_mean")
        payload["assumed_yaw_deg"] = (
            float(chosen.get("coarse_dx") or 0.0) / max(int(chosen.get("frame_w") or 1), 1)
        ) * FOV_H_DEG_ASSUMED
        payload["total_features"] = chosen.get("total_features")
        payload["valid_inliers"] = chosen.get("valid_inliers")
        payload["inlier_ratio"] = chosen.get("inlier_ratio")
        payload["physical"] = bool(chosen.get("physical"))
        payload["klt_physical"] = bool(chosen.get("klt_physical"))
        payload["coarse_physical"] = bool(chosen.get("coarse_physical"))
        block = v3_motion_block(
            mechanism=str(chosen.get("mechanism")),
            klt=dict(chosen),
            mouse_dx=float(mouse_dx) if chosen.get("mechanism") == "rmb_drag" else 0.0,
            frame_width=int(chosen.get("frame_w") or 1),
        )
        payload["px_cam_per_px_mouse"] = block["px_cam_per_px_mouse"]
        payload["deg_per_mouse_px"] = block["deg_per_mouse_px"]
        payload["reliable"] = bool(block["reliable"])
        payload["q5_closed"] = bool(block["q5_closed"])
        payload["motion"] = block
        payload["ok"] = True
        add_step(
            "done",
            mechanism=payload["mechanism"],
            physical=payload["physical"],
            q5_closed=payload["q5_closed"],
            median_dx=payload["median_dx"],
        )
        allow = bool(write_profile and block["reliable"])
        return _finish_v3(payload, out_path, clock, started, backend, write_profile=allow, profile_path=profile_path)
    except Exception as exc:  # noqa: BLE001 — always release HID and write a report
        payload["aborted"] = payload.get("aborted") or f"error:{type(exc).__name__}"
        add_step("abort", reason=payload["aborted"], error=str(exc)[:200])
        return _finish_v3(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
    finally:
        if own_grabber:
            grabber.close()


def _finish_v3(
    payload: dict[str, Any],
    out_path: Path | None,
    clock: Callable[[], int],
    started: int,
    backend: CGEventInputBackend | None,
    *,
    write_profile: bool,
    profile_path: Path,
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
            payload.get("watchdog_tripped")
            or any(row.reason == "watchdog_timeout" for row in backend.log)
        )
        payload["events"] = backend.events()
        payload["hid_sent"] = bool(payload.get("hid_sent") or any(row.hid_sent for row in backend.log))
    payload["session_ms"] = (clock() - started) / 1_000_000.0
    if write_profile and payload.get("motion") and payload.get("reliable") and profile_path.exists():
        write_profile_motion(profile_path, payload["motion"])
        payload["profile_written"] = str(profile_path)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["out"] = str(out_path)
    return payload


def dump_analysis_pair(
    t0: np.ndarray,
    t1: np.ndarray,
    dump_dir: Path,
    *,
    prefix: str | None = None,
    also: list[Path] | None = None,
) -> dict[str, str]:
    c0 = analysis_crop(t0)
    c1 = analysis_crop(t1)
    stem = f"calibration_{prefix}_" if prefix else "calibration_"
    p0 = dump_dir / f"{stem}t0.png"
    p1 = dump_dir / f"{stem}t1.png"
    write_png(p0, c0)
    write_png(p1, c1)
    for folder in also or ():
        write_png(folder / "calibration_t0.png", c0)
        write_png(folder / "calibration_t1.png", c1)
    return {"t0": str(p0), "t1": str(p1)}


def _publish_canonical_dumps(dumps: dict[str, str], dump_dir: Path, out_path: Path | None) -> dict[str, str]:
    src0 = Path(dumps.get("t0") or "")
    src1 = Path(dumps.get("t1") or "")
    canon0 = dump_dir / "calibration_t0.png"
    canon1 = dump_dir / "calibration_t1.png"
    if src0.is_file():
        dump_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src0, canon0)
    if src1.is_file():
        dump_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src1, canon1)
    published = {"t0": str(canon0), "t1": str(canon1), "attempt_t0": str(src0), "attempt_t1": str(src1)}
    if out_path is not None and "docs/evidence" in str(out_path):
        ev = Path("docs/evidence/live-s4")
        ev.mkdir(parents=True, exist_ok=True)
        if src0.is_file():
            shutil.copy2(src0, ev / "calibration_t0.png")
        if src1.is_file():
            shutil.copy2(src1, ev / "calibration_t1.png")
        published["evidence_t0"] = str(ev / "calibration_t0.png")
        published["evidence_t1"] = str(ev / "calibration_t1.png")
    return published


def run_sync_diag_calibration(
    *,
    live: bool,
    danger_confirmed: bool,
    window_id: int | None = None,
    target_pid: int | None = None,
    profile_path: Path = DEFAULT_PROFILE,
    out_path: Path | None = DEFAULT_OUT_SYNC,
    dump_dir: Path = DEFAULT_DUMP_DIR,
    write_profile: bool = False,
    grabber: Any | None = None,
    backend: CGEventInputBackend | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    now_ns: Callable[[], int] | None = None,
    focus_probe: Callable[[], bool] | None = None,
    mouse_dx: float = SYNC_RMB_DX,
    hold_ms: int = SYNC_HOLD_MS,
) -> dict[str, Any]:
    clock = now_ns or mono_ns
    started = clock()
    payload: dict[str, Any] = {
        "ok": False,
        "live": bool(live and danger_confirmed),
        "aborted": None,
        "window_id": window_id,
        "target_pid": target_pid,
        "algorithm": "klt_ransac",
        "attempts": [],
        "mechanism": None,
        "median_dx": None,
        "klt_median_dx": None,
        "diff_mean": None,
        "time_delta_ms": None,
        "ts_t0": None,
        "ts_t1": None,
        "unique_frame": None,
        "shares_memory": None,
        "identical_frames_error": False,
        "sck_desync": None,
        "total_features": None,
        "valid_inliers": None,
        "inlier_ratio": None,
        "physical": False,
        "reliable": False,
        "q5_closed": False,
        "q5_gt_yaw": False,
        "h8_closed": True,
        "hid_sent": False,
        "stuck_keys_count": 0,
        "watchdog_tripped": False,
        "ticks": 0,
        "session_ms": 0.0,
        "steps": [],
        "events": [],
        "farm": False,
        "profile_written": None,
        "dumps": None,
        "window": None,
    }
    steps: list[dict[str, Any]] = payload["steps"]

    def add_step(name: str, **extra: Any) -> None:
        row = {"step": name, "t_ms": (clock() - started) / 1_000_000.0, **extra}
        steps.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    if not live or not danger_confirmed:
        payload["aborted"] = "live_flags_required"
        return _finish_v3(payload, out_path, clock, started, None, write_profile=False, profile_path=profile_path)
    if grabber is None and (window_id is None or int(window_id) < 1):
        payload["aborted"] = "window_id_required"
        return _finish_v3(payload, out_path, clock, started, None, write_profile=False, profile_path=profile_path)

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
            return _finish_v3(payload, out_path, clock, started, None, write_profile=False, profile_path=profile_path)
        payload["target_pid"] = pid
        backend = CGEventInputBackend(
            pid,
            live_confirmed=True,
            live_danger_confirmed=True,
            profile=s4_input_profile(),
            focus_probe=focus_probe or is_allowed_frontmost,
        )
    assert backend is not None
    payload["window"] = attach_window_geometry(backend, window_id)
    focus = focus_probe or backend.check_window_focus

    def expired() -> bool:
        return (clock() - started) / 1_000_000_000.0 >= SYNC_MAX_SESSION_S

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
        payload["ticks"] = int(payload["ticks"]) + 1
        return image, ts

    def measure(name: str, fire: Callable[[], Any], input_duration_ns: int, *, release_rmb: bool) -> dict[str, Any] | None:
        before = shot()
        if before is None:
            add_step("abort", reason=payload.get("aborted"), attempt=name)
            return None
        t0, ts0 = before
        ev = fire()
        payload["hid_sent"] = bool(payload.get("hid_sent") or getattr(ev, "hid_sent", False))
        if getattr(ev, "reason", None) == "kill_switch":
            payload["aborted"] = "kill_switch"
            add_step("abort", reason="kill_switch", attempt=name)
            return None
        if not getattr(ev, "accepted", False):
            payload["aborted"] = getattr(ev, "reason", "rejected")
            add_step("abort", reason=payload["aborted"], attempt=name)
            return None
        add_step(name, accepted=True, reason=getattr(ev, "reason", None), ts_t0=ts0)

        def must_shot() -> tuple[np.ndarray, int]:
            got = shot()
            if got is None:
                raise RuntimeError("no frame")
            return got

        try:
            t1, ts1, unique = wait_unique_frame(
                must_shot,
                ts0,
                input_duration_ns,
                sleeper=sleeper,
                now_ns=clock,
                pump=backend.pump,
                settle_s=SYNC_SETTLE_S,
            )
        except (CaptureError, RuntimeError):
            if release_rmb:
                backend.rmb_up()
            add_step("abort", reason=payload.get("aborted") or "capture_lost", attempt=name)
            return None
        if release_rmb:
            backend.rmb_up()
        if payload.get("aborted"):
            add_step("abort", reason=payload.get("aborted"), attempt=name)
            return None
        diff = pixel_diff_mean(t0, t1)
        identical = bool(diff == 0.0)
        shared = bool(np.shares_memory(t0, t1))
        dumps = dump_analysis_pair(t0, t1, dump_dir, prefix=name)
        if identical:
            payload["identical_frames_error"] = True
            payload["aborted"] = "identical_frames_error"
            row = {
                "mechanism": name,
                "diff_mean": diff,
                "time_delta_ms": (ts1 - ts0) / 1_000_000.0,
                "ts_t0": ts0,
                "ts_t1": ts1,
                "unique_frame": unique,
                "shares_memory": shared,
                "identical_frames_error": True,
                "dumps": dumps,
            }
            payload["attempts"].append(row)
            add_step("identical_frames_error", **row)
            return None
        est = estimate_yaw_klt(t0, t1, profile_path=profile_path)
        row = {
            **est.to_dict(),
            "mechanism": name,
            "frame_w": int(t0.shape[1]),
            "physical": bool(est.reliable and abs(est.median_dx) >= PHYSICAL_DX_MIN),
            "diff_mean": diff,
            "time_delta_ms": (ts1 - ts0) / 1_000_000.0,
            "ts_t0": ts0,
            "ts_t1": ts1,
            "unique_frame": unique,
            "shares_memory": shared,
            "identical_frames_error": False,
            "dumps": dumps,
        }
        payload["attempts"].append(row)
        add_step("klt", **row)
        return row

    try:
        if not focus():
            payload["aborted"] = "focus_not_parallels"
            add_step("abort", reason="focus_not_parallels")
            return _finish_v3(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        grabber.start()
        add_step(
            "capture_start",
            work_y=[WORK_Y0, WORK_Y1],
            work_x=[WORK_X0, WORK_X1],
            mouse_dx=mouse_dx,
            hold_ms=hold_ms,
            settle_s=SYNC_SETTLE_S,
        )
        rmb_ns = int((RMB_STEPS * RMB_STEP_S) * 1_000_000_000)
        rmb = measure(
            "rmb_drag_hold",
            lambda: backend.rmb_drag(
                mouse_dx,
                steps=RMB_STEPS,
                step_delay_s=RMB_STEP_S,
                sleeper=sleeper,
                release=False,
            ),
            rmb_ns,
            release_rmb=True,
        )
        if payload.get("aborted"):
            return _finish_v3(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        chosen = rmb if rmb and rmb.get("physical") else None
        if chosen is None:
            arrow_ns = int(hold_ms * 1_000_000)
            pulse = measure(
                "arrow_hold",
                lambda: backend.hold_key_timed(
                    "right_arrow",
                    hold_ms,
                    sleeper=sleeper,
                    cap_ms=hold_ms,
                ),
                arrow_ns,
                release_rmb=False,
            )
            if payload.get("aborted"):
                return _finish_v3(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
            if pulse and pulse.get("physical"):
                chosen = pulse
        if chosen is None and payload["attempts"]:
            chosen = max(
                payload["attempts"],
                key=lambda row: (abs(float(row.get("median_dx") or 0.0)), float(row.get("diff_mean") or 0.0)),
            )
        if chosen is None:
            payload["aborted"] = payload.get("aborted") or "no_measurement"
            return _finish_v3(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
        payload["dumps"] = _publish_canonical_dumps(chosen.get("dumps") or {}, dump_dir, out_path)
        payload["mechanism"] = chosen.get("mechanism")
        payload["median_dx"] = chosen.get("median_dx")
        payload["klt_median_dx"] = chosen.get("median_dx")
        payload["diff_mean"] = chosen.get("diff_mean")
        payload["time_delta_ms"] = chosen.get("time_delta_ms")
        payload["ts_t0"] = chosen.get("ts_t0")
        payload["ts_t1"] = chosen.get("ts_t1")
        payload["unique_frame"] = chosen.get("unique_frame")
        payload["shares_memory"] = chosen.get("shares_memory")
        payload["total_features"] = chosen.get("total_features")
        payload["valid_inliers"] = chosen.get("valid_inliers")
        payload["inlier_ratio"] = chosen.get("inlier_ratio")
        payload["physical"] = bool(chosen.get("physical"))
        unique = bool(chosen.get("unique_frame"))
        diff = float(chosen.get("diff_mean") or 0.0)
        dx = abs(float(chosen.get("median_dx") or 0.0))
        if not unique and dx < PHYSICAL_DX_MIN:
            payload["sck_desync"] = True
        elif unique and diff > 0.0 and dx < PHYSICAL_DX_MIN:
            payload["sck_desync"] = False
        elif unique and dx >= PHYSICAL_DX_MIN:
            payload["sck_desync"] = False
        else:
            payload["sck_desync"] = None
        block = v3_motion_block(
            mechanism=str(chosen.get("mechanism")),
            klt=dict(chosen),
            mouse_dx=float(mouse_dx) if str(chosen.get("mechanism")).startswith("rmb") else 0.0,
            frame_width=int(chosen.get("frame_w") or 1),
        )
        payload["px_cam_per_px_mouse"] = block["px_cam_per_px_mouse"]
        payload["deg_per_mouse_px"] = block["deg_per_mouse_px"]
        payload["reliable"] = bool(block["reliable"])
        payload["q5_closed"] = bool(block["q5_closed"])
        payload["motion"] = block
        payload["ok"] = True
        add_step(
            "done",
            mechanism=payload["mechanism"],
            physical=payload["physical"],
            q5_closed=payload["q5_closed"],
            median_dx=payload["median_dx"],
            diff_mean=payload["diff_mean"],
            time_delta_ms=payload["time_delta_ms"],
            sck_desync=payload["sck_desync"],
        )
        allow = bool(write_profile and block["reliable"])
        return _finish_v3(payload, out_path, clock, started, backend, write_profile=allow, profile_path=profile_path)
    except Exception as exc:  # noqa: BLE001 — always release HID and write a report
        payload["aborted"] = payload.get("aborted") or f"error:{type(exc).__name__}"
        add_step("abort", reason=payload["aborted"], error=str(exc)[:200])
        return _finish_v3(payload, out_path, clock, started, backend, write_profile=False, profile_path=profile_path)
    finally:
        if own_grabber:
            grabber.close()


def maybe_write_profile_if_gates(
    profile_path: Path,
    *,
    h8_p95_ms: float | None,
    yaw_peak: float | None,
    motion: dict[str, Any] | None,
    h8_threshold_ms: float = 100.0,
    peak_threshold: float = PEAK_RELIABLE,
) -> bool:
    """Write motion into the window profile only if H8 p95 and horizon peak both pass."""
    if motion is None or h8_p95_ms is None or yaw_peak is None:
        return False
    if float(yaw_peak) < float(peak_threshold):
        return False
    if float(h8_p95_ms) > float(h8_threshold_ms):
        return False
    if not profile_path.exists():
        return False
    block = dict(motion)
    block["h8_closed"] = True
    block["h8_p95_ms"] = float(h8_p95_ms)
    write_profile_motion(profile_path, block)
    return True


# SEARCH_HOLD_MAX_MS imported so a 500 ms pulse stays inside the existing cap.
assert HOLD_MS <= SEARCH_HOLD_MAX_MS
assert KLT_HOLD_MS <= SEARCH_HOLD_MAX_MS
