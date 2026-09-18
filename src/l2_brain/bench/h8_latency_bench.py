"""Live H8 latency. p95(observe+infer+act), not odometry. No farm."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.capture.errors import CaptureError
from l2_brain.contracts import Frame
from l2_brain.control.baseline import BaselineController
from l2_brain.experiment.clocks import mono_ns
from l2_brain.io.cgevent_backend import CGEventInputBackend
from l2_brain.io.focus import frontmost_app, is_allowed_frontmost
from l2_brain.live.s4_probe import SCKGrabber, s4_input_profile
from l2_brain.vision.encoder import NavigationEncoder
from l2_brain.vision.hud_parser import HUDParser

DEFAULT_PROFILE = Path("config/window_profiles/parallels_l2.json")
DEFAULT_OUT = Path("docs/evidence/live-s4/h8-latency-report.json")
H8_P95_MS = 100.0
H8_REJECT_MS = 150.0
INTENT_TTL_NS = 50_000_000


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(x) for x in values)
    idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return float(ordered[idx])


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "n": float(len(values)),
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": float(max(values)) if values else 0.0,
    }


def run_h8_bench(
    *,
    live: bool,
    danger_confirmed: bool,
    window_id: int | None = None,
    target_pid: int | None = None,
    samples: int = 100,
    warmup: int = 8,
    profile_path: Path = DEFAULT_PROFILE,
    out_path: Path | None = DEFAULT_OUT,
    grabber: Any | None = None,
    backend: CGEventInputBackend | None = None,
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
        "samples_requested": int(samples),
        "warmup": int(warmup),
        "h8_formula": "observe_ms + infer_ms + act_ms",
        "h8_threshold_ms": H8_P95_MS,
        "h8_reject_ms": H8_REJECT_MS,
        "h8_accepted": False,
        "h8_closed": False,
        "parse_in_h8": False,
        "encode_in_h8": False,
        "hid_sent": False,
        "act_posted": False,
        "stuck_keys_count": 0,
        "watchdog_tripped": False,
        "farm": False,
        "ticks": 0,
        "session_ms": 0.0,
        "samples": [],
    }
    if not live or not danger_confirmed:
        payload["aborted"] = "live_flags_required"
        return _finish(payload, out_path, clock, started, None)
    if grabber is None and (window_id is None or int(window_id) < 1):
        payload["aborted"] = "window_id_required"
        return _finish(payload, out_path, clock, started, None)
    if int(samples) < 1:
        payload["aborted"] = "samples_required"
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
    parser = HUDParser.from_profile(profile_path)
    encoder = NavigationEncoder()
    encoder.initialize()
    controller = BaselineController()
    controller.initialize()
    last_obs = None
    frame_id = 0

    try:
        if not focus():
            payload["aborted"] = "focus_not_parallels"
            return _finish(payload, out_path, clock, started, backend)
        grabber.start()
        total = int(warmup) + int(samples)
        kept: list[dict[str, float]] = []
        for i in range(total):
            if not focus():
                payload["aborted"] = "focus_lost"
                break
            backend.pump()
            t0 = time.perf_counter()
            try:
                image = grabber.latest_image()
            except (CaptureError, RuntimeError):
                payload["aborted"] = "capture_lost"
                break
            observe_ms = (time.perf_counter() - t0) * 1000.0
            if image is None or image.ndim != 3:
                payload["aborted"] = "empty_frame"
                break
            t1 = time.perf_counter()
            parser.parse(image)
            parse_ms = (time.perf_counter() - t1) * 1000.0
            now = clock()
            frame_id += 1
            frame = Frame(
                frame_id=frame_id,
                timestamp_capture_ns=now,
                timestamp_received_ns=now,
                width=int(image.shape[1]),
                height=int(image.shape[0]),
                pixel_format="rgb8",
                source_id="sck.window",
                image=np.ascontiguousarray(image),
            )
            t_enc = time.perf_counter()
            observation = encoder.encode(frame, (), last_obs, now, False)
            encode_ms = (time.perf_counter() - t_enc) * 1000.0
            t2 = time.perf_counter()
            controller.step(observation, now, INTENT_TTL_NS)
            infer_ms = (time.perf_counter() - t2) * 1000.0
            last_obs = observation
            t3 = time.perf_counter()
            act = backend.idle_act()
            act_ms = (time.perf_counter() - t3) * 1000.0
            payload["act_posted"] = True
            if act.get("killed"):
                payload["aborted"] = "kill_switch"
                break
            if not act.get("focused"):
                payload["aborted"] = "focus_lost"
                break
            h8_ms = observe_ms + infer_ms + act_ms
            pipeline_ms = observe_ms + parse_ms + infer_ms + act_ms
            payload["ticks"] = i + 1
            if i >= int(warmup):
                kept.append(
                    {
                        "observe_ms": observe_ms,
                        "parse_ms": parse_ms,
                        "encode_ms": encode_ms,
                        "infer_ms": infer_ms,
                        "act_ms": act_ms,
                        "h8_ms": h8_ms,
                        "pipeline_ms": pipeline_ms,
                    }
                )
        payload["samples"] = kept
        if payload.get("aborted"):
            return _finish(payload, out_path, clock, started, backend)
        if len(kept) < int(samples):
            payload["aborted"] = "short_sample"
            return _finish(payload, out_path, clock, started, backend)
        obs = [row["observe_ms"] for row in kept]
        parse = [row["parse_ms"] for row in kept]
        enc = [row["encode_ms"] for row in kept]
        inf = [row["infer_ms"] for row in kept]
        act = [row["act_ms"] for row in kept]
        h8 = [row["h8_ms"] for row in kept]
        pipe = [row["pipeline_ms"] for row in kept]
        payload["observe"] = summarize(obs)
        payload["parse"] = summarize(parse)
        payload["encode"] = summarize(enc)
        payload["infer"] = summarize(inf)
        payload["act"] = summarize(act)
        payload["h8"] = summarize(h8)
        payload["pipeline"] = summarize(pipe)
        p95 = float(payload["h8"]["p95"])
        payload["h8_p95_ms"] = p95
        payload["h8_accepted"] = p95 <= H8_P95_MS
        payload["h8_closed"] = bool(payload["h8_accepted"])
        payload["h8_rejected"] = p95 > H8_REJECT_MS
        payload["ok"] = True
        return _finish(payload, out_path, clock, started, backend)
    except Exception as exc:  # noqa: BLE001 — always release HID and write a report
        payload["aborted"] = payload.get("aborted") or f"error:{type(exc).__name__}"
        payload["error"] = str(exc)[:200]
        return _finish(payload, out_path, clock, started, backend)
    finally:
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
            backend.release_all()
        except Exception:  # noqa: BLE001 — report still writes
            pass
        payload["stuck_keys_count"] = len(backend.watchdog.active_holds)
        payload["watchdog_tripped"] = bool(
            payload.get("watchdog_tripped")
            or any(row.reason == "watchdog_timeout" for row in backend.log)
        )
        payload["hid_sent"] = bool(any(row.hid_sent for row in backend.log))
    payload["session_ms"] = (clock() - started) / 1_000_000.0
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["out"] = str(out_path)
    return payload
