"""T0/T1 isolation for yaw probes. Not a game client."""

from __future__ import annotations

import struct
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.calibration.klt_yaw import WORK_X0, WORK_X1, WORK_Y0, WORK_Y1

SETTLE_S = 0.30
POLL_S = 0.02
MAX_WAIT_S = 2.0


def analysis_crop(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    y0, y1 = int(round(h * WORK_Y0)), int(round(h * WORK_Y1))
    x0, x1 = int(round(w * WORK_X0)), int(round(w * WORK_X1))
    return np.ascontiguousarray(image[y0:y1, x0:x1]).copy()


def pixel_diff_mean(t0: np.ndarray, t1: np.ndarray) -> float:
    a = np.asarray(t0, dtype=np.int16)
    b = np.asarray(t1, dtype=np.int16)
    return float(np.mean(np.abs(b - a)))


def write_png(path: Path, rgb: np.ndarray) -> None:
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("write_png expects HxWx3 uint8")
    height, width = rgb.shape[:2]
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    )


def grab_shot(grabber: Any) -> tuple[np.ndarray, int]:
    if hasattr(grabber, "latest_shot"):
        image, ts = grabber.latest_shot()
        return np.ascontiguousarray(image).copy(), int(ts)
    image = np.ascontiguousarray(grabber.latest_image()).copy()
    return image, 0


def wait_unique_frame(
    grab: Callable[[], tuple[np.ndarray, int]],
    ts_t0: int,
    input_duration_ns: int,
    *,
    sleeper: Callable[[float], None],
    now_ns: Callable[[], int],
    pump: Callable[[], Any] | None = None,
    settle_s: float = SETTLE_S,
    max_wait_s: float = MAX_WAIT_S,
    poll_s: float = POLL_S,
) -> tuple[np.ndarray, int, bool]:
    """Sleep, then take frames until capture ts is after T0 + input duration."""
    sleeper(float(settle_s))
    need = int(ts_t0) + int(input_duration_ns)
    deadline = int(now_ns()) + int(max_wait_s * 1_000_000_000)
    last: tuple[np.ndarray, int] | None = None
    unique = False
    while int(now_ns()) <= deadline:
        if pump is not None:
            pump()
        image, ts = grab()
        last = (image, int(ts))
        if int(ts) > need:
            unique = True
            break
        sleeper(float(poll_s))
    if last is None:
        raise RuntimeError("no frame after wait")
    return last[0], last[1], unique
