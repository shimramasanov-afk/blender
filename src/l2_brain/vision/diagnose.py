from __future__ import annotations

from pathlib import Path

import numpy as np

from l2_brain.features import extract_from_image, red_mask
from l2_brain.vision.channels import NavigationChannels
from l2_brain.vision.flow import FlowField


def render_diag(
    gray: np.ndarray,
    field: FlowField,
    channels: NavigationChannels,
    *,
    target_x: float | None = None,
) -> np.ndarray:
    """Overlay flow, weak-texture marks, target, and confidence. Not a policy input."""
    height, width = gray.shape
    rgb = np.stack([gray, gray, gray], axis=2).astype(np.uint8)
    scale = 2
    canvas = np.repeat(np.repeat(rgb, scale, axis=0), scale, axis=1)
    ny, nx = field.u.shape
    for j in range(ny):
        for i in range(nx):
            x = int(field.xs[j, i] * scale)
            y = int(field.ys[j, i] * scale)
            if field.weak_texture[j, i]:
                _cross(canvas, x, y, (80, 80, 80))
                continue
            if field.confidence[j, i] < 0.08:
                continue
            dx = int(round(field.u[j, i] * scale))
            dy = int(round(field.v[j, i] * scale))
            _arrow(canvas, x, y, x + dx, y + dy, (40, 200, 70))
    _sector_bars(canvas, channels)
    if target_x is not None:
        tx = int(target_x * canvas.shape[1])
        _arrow(canvas, canvas.shape[1] // 2, 8, tx, 8, (220, 40, 220))
    _confidence_strip(canvas, channels.motion_confidence)
    _expansion_strip(canvas, channels.expansion)
    _label_mark(canvas, channels.hypothesis.label)
    return canvas


def render_target_debug(image: np.ndarray, *, min_conf: float = 0.12) -> tuple[np.ndarray, dict[str, float | int | bool]]:
    """Mask + confidence. Does not change detection thresholds."""
    mask = red_mask(image)
    blob = extract_from_image(image)
    conf = min(1.0, blob.mass * 8.0) if blob.seen else 0.0
    canvas = image.copy()
    overlay = canvas.astype(np.int16)
    overlay[mask] = overlay[mask] * 0.45 + np.array([40, 220, 40], dtype=np.int16)
    canvas = np.clip(overlay, 0, 255).astype(np.uint8)
    pixels = int(mask.sum())
    info = {
        "pixels": pixels,
        "mass": float(blob.mass),
        "confidence": float(conf),
        "seen": bool(blob.seen),
        "above_policy_threshold": bool(conf >= min_conf),
        "threshold_unchanged": True,
    }
    return canvas, info


def write_ppm(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"P6\n{image.shape[1]} {image.shape[0]}\n255\n"
    path.write_bytes(header.encode("ascii") + np.ascontiguousarray(image, dtype=np.uint8).tobytes())


def _arrow(img: np.ndarray, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for t in range(n + 1):
        x = int(x0 + (x1 - x0) * t / n)
        y = int(y0 + (y1 - y0) * t / n)
        _dot(img, x, y, color)


def _cross(img: np.ndarray, x: int, y: int, color: tuple[int, int, int]) -> None:
    for d in range(-2, 3):
        _dot(img, x + d, y + d, color)
        _dot(img, x + d, y - d, color)


def _dot(img: np.ndarray, x: int, y: int, color: tuple[int, int, int]) -> None:
    if 0 <= y < img.shape[0] and 0 <= x < img.shape[1]:
        img[y, x] = color


def _sector_bars(img: np.ndarray, channels: NavigationChannels) -> None:
    values = channels.far.brightness
    if not values:
        return
    bar_h = 4
    width = img.shape[1]
    n = len(values)
    for i, value in enumerate(values):
        x0 = i * width // n
        x1 = (i + 1) * width // n
        level = int(max(0.0, min(1.0, value)) * (bar_h * 6))
        img[0:bar_h, x0:x1] = (int(40 + 180 * value), 160, 40)
        _ = level


def _confidence_strip(img: np.ndarray, confidence: float) -> None:
    width = max(1, int(img.shape[1] * max(0.0, min(1.0, confidence))))
    img[-3:, :width] = (30, 80, 220)
    img[-3:, width:] = (20, 20, 20)


def _expansion_strip(img: np.ndarray, expansion: float) -> None:
    mid = img.shape[1] // 2
    span = int(img.shape[1] * 0.5 * max(-1.0, min(1.0, expansion / 0.16)))
    img[-6:-3, :] = (20, 20, 20)
    if span >= 0:
        img[-6:-3, mid : mid + span] = (40, 200, 90)
    else:
        img[-6:-3, mid + span : mid] = (200, 80, 40)


def _label_mark(img: np.ndarray, label: str) -> None:
    colors = {
        "approach": (40, 200, 90),
        "camera_turn": (40, 160, 220),
        "low_confidence": (200, 160, 40),
        "uncertain": (160, 160, 160),
    }
    img[4:10, -10:-4] = colors.get(label, (120, 120, 120))
