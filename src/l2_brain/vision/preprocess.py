from __future__ import annotations

import numpy as np

from l2_brain.capture.masks import apply_profile
from l2_brain.capture.profile import WindowProfile
from l2_brain.vision.config import VisionConfig


def to_gray(image: np.ndarray) -> np.ndarray:
    rgb = image.astype(np.float32)
    return 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]


def resize(image: np.ndarray, height: int, width: int) -> np.ndarray:
    if image.shape[0] == height and image.shape[1] == width:
        return image
    ys = np.linspace(0, image.shape[0] - 1, height).astype(np.int32)
    xs = np.linspace(0, image.shape[1] - 1, width).astype(np.int32)
    if image.ndim == 2:
        return np.ascontiguousarray(image[ys][:, xs])
    return np.ascontiguousarray(image[ys][:, xs, :])


def prepare(image: np.ndarray, config: VisionConfig, profile: WindowProfile | None) -> np.ndarray:
    work = image
    if profile is not None:
        work = apply_profile(work, profile)
    gray = to_gray(work)
    return resize(gray, config.height, config.width)


def sector_stats(plane: np.ndarray, sx: int, sy: int) -> tuple[tuple[float, ...], tuple[float, ...]]:
    height, width = plane.shape
    means: list[float] = []
    contrasts: list[float] = []
    for iy in range(sy):
        for ix in range(sx):
            y0, y1 = iy * height // sy, (iy + 1) * height // sy
            x0, x1 = ix * width // sx, (ix + 1) * width // sx
            tile = plane[y0:y1, x0:x1]
            means.append(float(tile.mean()))
            contrasts.append(float(tile.std()))
    return tuple(means), tuple(contrasts)


def normalize_01(gray: np.ndarray) -> np.ndarray:
    return np.clip(gray / 255.0, 0.0, 1.0)


def scene_correlation(prev: np.ndarray, curr: np.ndarray) -> float:
    """Same-scene score after a box downsample so a small shift is not a cut."""
    aa = _coarse(prev)
    bb = _coarse(curr)
    aa = aa - aa.mean()
    bb = bb - bb.mean()
    denom = float(np.sqrt((aa * aa).sum() * (bb * bb).sum())) + 1e-6
    best = float((aa * bb).sum() / denom)
    for dx in (-2, -1, 1, 2):
        rolled = np.roll(bb, dx, axis=1)
        best = max(best, float((aa * rolled).sum() / denom))
    return best


def _coarse(gray: np.ndarray, cell: int = 4) -> np.ndarray:
    plane = gray.astype(np.float32)
    h, w = plane.shape
    hh, ww = (h // cell) * cell, (w // cell) * cell
    if hh < cell * 2 or ww < cell * 2:
        return plane[::2, ::2]
    cropped = plane[:hh, :ww]
    return cropped.reshape(hh // cell, cell, ww // cell, cell).mean(axis=(1, 3))
