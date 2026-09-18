from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, IO

import numpy as np

from l2_brain.capture.errors import CaptureError, PermissionDenied, SourceLost
from l2_brain.capture.helper import resolve_helper
from l2_brain.capture.masks import apply_profile
from l2_brain.capture.profile import WindowProfile
from l2_brain.capture.wire import read_packet
from l2_brain.contracts import Frame
from l2_brain.experiment.clocks import event_ns
from l2_brain.experiment.queues import LatestOnlyQueue, QueueEmpty

COPIES = {
    "sck_gpu_to_cpu": "unknown_not_counted",
    "helper_bgra_to_rgb": 1,
    "pipe_write": 1,
    "python_read": 1,
    "ndarray_own": 1,
    "total_counted": 4,
    "shared_memory": False,
}


@dataclass
class SCKConfig:
    helper_path: Path | None = None
    window_id: int | None = None
    self_test: bool = False
    fps: int = 60
    max_frames: int = 0
    resize: bool = False
    profile_path: Path | None = None
    latest_timeout_s: float = 2.5
    source_id: str = "sck.window"
    build_helper: bool = False
    helper_command: list[str] | None = None


@dataclass
class SCKFrameSource:
    """Circuit FrameSource backed by the ScreenCaptureKit helper over a pipe."""

    config: SCKConfig
    profile: WindowProfile = field(default_factory=WindowProfile.generic)
    last_stats: dict[str, Any] = field(default_factory=dict)
    last_header: dict[str, Any] | None = None
    queue_drops: int = 0

    def __post_init__(self) -> None:
        if self.config.profile_path is not None:
            self.profile = WindowProfile.load(self.config.profile_path)
        self._open = False
        self._proc: subprocess.Popen[bytes] | None = None
        self._reader: threading.Thread | None = None
        self._queue: LatestOnlyQueue[tuple[dict[str, Any], bytes]] = LatestOnlyQueue()
        self._lost: str | None = None
        self._hello: dict[str, Any] | None = None
        self._stderr = ""
        self._frame_id = 1
        self._bytes = 0
        self._resizes = 0

    def initialize(self) -> None:
        if (
            self.config.helper_command is None
            and self.config.self_test is False
            and self.config.window_id is None
        ):
            raise CaptureError("SCKFrameSource needs window_id or self_test")
        if self.config.helper_command:
            cmd = list(self.config.helper_command)
        else:
            helper = resolve_helper(self.config.helper_path, build=self.config.build_helper)
            cmd = [str(helper)]
            if helper.suffix == ".py":
                cmd = [sys.executable, str(helper)]
            if self.config.self_test:
                cmd.extend(["--self-test", "--fps", str(self.config.fps)])
                if self.config.max_frames:
                    cmd.extend(["--max-frames", str(self.config.max_frames)])
                if self.config.resize:
                    cmd.append("--resize")
            else:
                cmd.extend(
                    [
                        "--stream",
                        "--window-id",
                        str(self.config.window_id),
                        "--fps",
                        str(self.config.fps),
                    ]
                )
                if self.config.max_frames:
                    cmd.extend(["--max-frames", str(self.config.max_frames)])
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        assert self._proc.stdout is not None
        self._open = True
        self._lost = None
        self._reader = threading.Thread(target=self._read_loop, args=(self._proc.stdout,), daemon=True)
        self._reader.start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def reset_episode(self, seed: int | None = None) -> None:
        self._queue.clear()
        self._frame_id = 1

    def latest(self) -> Frame:
        if not self._open:
            raise RuntimeError("SCKFrameSource is closed")
        try:
            header, payload = self._queue.take()
        except QueueEmpty:
            if self._lost:
                raise SourceLost(self._lost)
            try:
                header, payload = self._queue.take_wait(self.config.latest_timeout_s)
            except QueueEmpty as exc:
                if self._lost:
                    raise SourceLost(self._lost) from exc
                if self._proc is not None and self._proc.poll() is not None:
                    raise SourceLost(self._stderr or "helper exited") from exc
                raise CaptureError("no frame from ScreenCaptureKit helper") from exc
        self.last_header = header
        self.queue_drops = self._queue.drops
        image = np.frombuffer(payload, dtype=np.uint8).copy()
        width = int(header["width"])
        height = int(header["height"])
        image = image.reshape((height, width, 3))
        image = apply_profile(image, self.profile)
        received = event_ns()
        capture = int(header.get("host_unix_ns") or received)
        self._bytes += int(header.get("bytes") or payload.__len__())
        self.last_stats = {
            "copies": COPIES,
            "helper_drops": int(header.get("drops") or 0),
            "python_queue_drops": self._queue.drops,
            "bytes": int(header.get("bytes") or 0),
            "pixel_format": header.get("pixel_format"),
            "copy_ms": header.get("copy_ms"),
            "scale": header.get("scale"),
            "sck_pts_ns": header.get("sck_pts_ns"),
            "sck_pts_clock": header.get("sck_pts_clock"),
            "requested_fps": self.config.fps,
            "requested_fps_is_not_a_guarantee": True,
            "profile_id": self.profile.profile_id,
            "resizes": self._resizes,
        }
        frame = Frame(
            frame_id=self._frame_id,
            timestamp_capture_ns=capture,
            timestamp_received_ns=received,
            width=image.shape[1],
            height=image.shape[0],
            pixel_format="rgb8",
            source_id=str(header.get("source_id") or self.config.source_id),
            image=image,
            clock_id="event",
        )
        self._frame_id += 1
        return frame

    def close(self) -> None:
        self._open = False
        if self._proc is not None and self._proc.poll() is None:
            self._proc.send_signal(15)
            try:
                self._proc.wait(timeout=2.5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=1.0)
        if self._reader is not None:
            self._reader.join(timeout=2.0)
        self._proc = None

    def _read_loop(self, stdout: IO[bytes]) -> None:
        try:
            while True:
                packet = read_packet(stdout)
                if packet is None:
                    if self._lost is None:
                        self._lost = self._stderr or "helper closed stdout"
                    break
                header, payload = packet
                kind = header.get("kind")
                if kind == "hello":
                    self._hello = header
                elif kind == "frame":
                    self._queue.put((header, payload))
                elif kind == "resize":
                    self._resizes += 1
                    self.last_stats = {**self.last_stats, "last_resize": header}
                elif kind == "source_lost":
                    self._lost = str(header.get("reason") or "source lost")
                    break
                elif kind == "stats":
                    self.last_stats = {**self.last_stats, "helper_stats": header}
                elif kind == "permission" and header.get("status") == "denied":
                    self._lost = header.get("hint") or "Screen Recording denied"
                    break
        except Exception as exc:  # noqa: BLE001 — reader must never kill the process
            self._lost = str(exc)

    def _drain_stderr(self) -> None:
        if self._proc is None or self._proc.stderr is None:
            return
        chunks: list[str] = []
        for line in self._proc.stderr:
            chunks.append(line.decode("utf-8", errors="replace"))
        self._stderr = "".join(chunks)


def capture_metrics(source: SCKFrameSource, received_ns: list[int] | None = None) -> dict[str, Any]:
    stamps = received_ns or []
    intervals = []
    for prev, cur in zip(stamps, stamps[1:], strict=False):
        intervals.append((cur - prev) / 1_000_000.0)
    rss = 0
    try:
        rss = int(os.popen(f"ps -o rss= -p {os.getpid()}").read().strip() or 0) * 1024
    except (OSError, ValueError):
        rss = 0
    return {
        "frames": len(stamps),
        "median_interval_ms": _median(intervals),
        "achieved_fps": (1000.0 / _median(intervals)) if intervals and _median(intervals) > 0 else 0.0,
        "requested_fps": source.config.fps,
        "requested_fps_is_not_a_guarantee": True,
        "bytes_total": source._bytes,
        "pixel_format": "rgb8",
        "copies": COPIES,
        "queue_drops": source.queue_drops,
        "resizes": source._resizes,
        "python_rss_bytes": rss,
        "last_stats": source.last_stats,
        "transport": "stdout_pipe",
        "shared_memory": False,
        "h7_30s_window": False,
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])
