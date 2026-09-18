"""H7 probe: timestamps and frame quality. No HID. No policy."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.capture.errors import CaptureError, SourceLost
from l2_brain.capture.helper import list_windows, resolve_helper
from l2_brain.capture.sck import SCKConfig, SCKFrameSource

BLACK_MEAN = 4.0
BLACK_MAX = 12.0


def is_black_frame(image: np.ndarray) -> bool:
    return float(image.mean()) < BLACK_MEAN and float(image.max()) < BLACK_MAX


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    return float(np.quantile(np.asarray(values, dtype=np.float64), q))


def h7_verdict(*, median_interval_ms: float, drop_rate: float, black_rate: float) -> dict[str, Any]:
    hard_reject = median_interval_ms > 80.0 or black_rate >= 0.10
    accepted = median_interval_ms <= 50.0 and drop_rate < 0.10 and black_rate < 0.05
    if hard_reject:
        status = "rejected"
    elif accepted:
        status = "accepted"
    else:
        status = "not_accepted"
    return {
        "h7_accepted": accepted,
        "h7_status": status,
        "median_interval_ms": median_interval_ms,
        "drop_rate": drop_rate,
        "black_frame_rate": black_rate,
    }


def resolve_visible_window(
    windows: list[dict[str, Any]],
    *,
    window_id: int | None = None,
    title: str | None = None,
    bundle_id: str | None = None,
) -> dict[str, Any] | None:
    visible = [row for row in windows if row.get("on_screen")]
    if window_id is not None:
        for row in visible:
            if int(row.get("id") or 0) == window_id:
                return row
    if title and bundle_id:
        for row in visible:
            if row.get("title") == title and row.get("bundle") == bundle_id and float(row.get("height") or 0) >= 200:
                return row
    return None


def run_h7_probe(
    *,
    window_id: int,
    duration_s: float = 30.0,
    fps: int = 30,
    profile_path: Path | None = None,
    helper_path: Path | None = None,
) -> dict[str, Any]:
    if duration_s < 1.0:
        raise ValueError("duration_s must be >= 1")
    helper = resolve_helper(helper_path, build=True)
    catalog = list_windows(helper)
    title = bundle_id = None
    if profile_path is not None:
        mapping = json.loads(Path(profile_path).read_text(encoding="utf-8"))
        title = mapping.get("window_title")
        bundle_id = mapping.get("bundle_id")
    resolved = resolve_visible_window(
        list(catalog.get("windows") or []),
        window_id=window_id,
        title=title,
        bundle_id=bundle_id,
    )
    if resolved is None:
        offspace = [
            row
            for row in list(catalog.get("windows") or [])
            if int(row.get("id") or 0) == window_id
            or (
                title
                and bundle_id
                and row.get("title") == title
                and row.get("bundle") == bundle_id
                and float(row.get("height") or 0) >= 200
            )
        ]
        verdict = h7_verdict(median_interval_ms=0.0, drop_rate=1.0, black_rate=1.0)
        return {
            "suite": "h7-visible-window",
            "hypothesis": "H7: visible window median interval <= 50 ms, drop < 0.10, black < 0.05 over 30 s.",
            "window_id": window_id,
            "offspace_candidates": offspace,
            "duration_s_requested": duration_s,
            "duration_s_elapsed": 0.0,
            "source_lost": f"window {window_id} not among on-screen windows",
            "h7_30s_window": False,
            "requested_fps": fps,
            "requested_fps_is_not_a_guarantee": True,
            "frames": 0,
            "width": 0,
            "height": 0,
            "median_interval_ms": 0.0,
            "achieved_fps": 0.0,
            "drops_ratio": 1.0,
            "helper_drops": 0,
            "python_queue_drops": 0,
            "black_frames": 0,
            "black_frames_ratio": 1.0,
            "mean_luma_p50": 0.0,
            "capture_latency_ms_p50": 0.0,
            "capture_latency_ms_p95": 0.0,
            "transport": "stdout_pipe",
            "shared_memory": False,
            "hidden_window": bool(offspace),
            "hid_sent": False,
            "dry_run": True,
            "transfer_claim": False,
            "last_stats": {},
            **verdict,
        }
    window_id = int(resolved["id"])
    source = SCKFrameSource(
        SCKConfig(
            helper_path=helper,
            window_id=window_id,
            fps=fps,
            max_frames=0,
            profile_path=profile_path,
            latest_timeout_s=5.0,
        )
    )
    latencies: list[float] = []
    received: list[int] = []
    means: list[float] = []
    black = 0
    width = height = 0
    t0 = time.monotonic()
    source.initialize()
    lost: str | None = None
    try:
        deadline = t0 + duration_s
        while time.monotonic() < deadline:
            try:
                frame = source.latest()
            except (SourceLost, CaptureError) as exc:
                lost = str(exc)
                break
            if frame.image is None:
                continue
            width, height = frame.width, frame.height
            received.append(frame.timestamp_received_ns)
            latencies.append((frame.timestamp_received_ns - frame.timestamp_capture_ns) / 1_000_000.0)
            means.append(float(frame.image.mean()))
            if is_black_frame(frame.image):
                black += 1
    finally:
        helper_drops = int(source.last_stats.get("helper_drops") or 0)
        queue_drops = int(source.queue_drops)
        last_stats = dict(source.last_stats)
        source.close()
    elapsed = time.monotonic() - t0
    intervals = [
        (cur - prev) / 1_000_000.0 for prev, cur in zip(received, received[1:], strict=False)
    ]
    n = len(received)
    drop_den = n + queue_drops + helper_drops
    drop_rate = (queue_drops + helper_drops) / drop_den if drop_den else 1.0
    black_rate = black / n if n else 1.0
    median = _percentile(intervals, 0.50)
    complete = elapsed >= duration_s - 0.5 and lost is None
    verdict = h7_verdict(median_interval_ms=median, drop_rate=drop_rate, black_rate=black_rate)
    if not complete:
        verdict["h7_accepted"] = False
        if n == 0 or black_rate >= 0.10:
            verdict["h7_status"] = "rejected"
        elif verdict["h7_status"] == "accepted":
            verdict["h7_status"] = "not_accepted"
    return {
        "suite": "h7-visible-window",
        "hypothesis": "H7: visible window median interval <= 50 ms, drop < 0.10, black < 0.05 over 30 s.",
        "window_id": window_id,
        "window_title": resolved.get("title"),
        "window_bundle": resolved.get("bundle"),
        "duration_s_requested": duration_s,
        "duration_s_elapsed": elapsed,
        "source_lost": lost,
        "h7_30s_window": complete and duration_s >= 29.0,
        "requested_fps": fps,
        "requested_fps_is_not_a_guarantee": True,
        "frames": n,
        "width": width,
        "height": height,
        "median_interval_ms": median,
        "achieved_fps": (1000.0 / median) if median > 0 else 0.0,
        "drops_ratio": drop_rate,
        "helper_drops": helper_drops,
        "python_queue_drops": queue_drops,
        "black_frames": black,
        "black_frames_ratio": black_rate,
        "mean_luma_p50": _percentile(means, 0.50),
        "capture_latency_ms_p50": _percentile(latencies, 0.50),
        "capture_latency_ms_p95": _percentile(latencies, 0.95),
        "transport": "stdout_pipe",
        "shared_memory": False,
        "hidden_window": False,
        "hid_sent": False,
        "dry_run": True,
        "transfer_claim": False,
        "last_stats": last_stats,
        **verdict,
    }


def write_h7_report(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
