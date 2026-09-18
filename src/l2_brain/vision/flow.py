from __future__ import annotations

from dataclasses import dataclass
from math import hypot

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from l2_brain.vision.config import VisionConfig


@dataclass(frozen=True, slots=True)
class FlowField:
    u: np.ndarray
    v: np.ndarray
    confidence: np.ndarray
    weak_texture: np.ndarray
    xs: np.ndarray
    ys: np.ndarray


def reference_flow(prev: np.ndarray, curr: np.ndarray, config: VisionConfig) -> FlowField:
    """Coarse block-matching. CPU reference, not a learned model."""
    height, width = prev.shape
    nx, ny = config.flow_nx, config.flow_ny
    block, search = config.flow_block, config.flow_search
    half = block // 2
    u = np.zeros((ny, nx), dtype=np.float32)
    v = np.zeros((ny, nx), dtype=np.float32)
    conf = np.zeros((ny, nx), dtype=np.float32)
    weak = np.zeros((ny, nx), dtype=bool)
    xs = np.zeros((ny, nx), dtype=np.float32)
    ys = np.zeros((ny, nx), dtype=np.float32)
    prev_i = np.asarray(prev, dtype=np.int16)
    curr_i = np.asarray(curr, dtype=np.int16)
    for j in range(ny):
        cy = int((j + 0.5) * height / ny)
        for i in range(nx):
            cx = int((i + 0.5) * width / nx)
            xs[j, i] = cx
            ys[j, i] = cy
            y0, x0 = cy - half, cx - half
            y1, x1 = y0 + block, x0 + block
            if y0 < 0 or x0 < 0 or y1 > height or x1 > width:
                weak[j, i] = True
                continue
            templ = prev_i[y0:y1, x0:x1]
            variance = float(templ.var())
            if variance < config.texture_var:
                weak[j, i] = True
                continue
            sy0 = max(0, y0 - search)
            sx0 = max(0, x0 - search)
            sy1 = min(height, y1 + search)
            sx1 = min(width, x1 + search)
            windows = sliding_window_view(curr_i[sy0:sy1, sx0:sx1], (block, block))
            if windows.size == 0:
                weak[j, i] = True
                continue
            sad = np.mean(np.abs(windows.astype(np.int32) - templ), axis=(-2, -1))
            dys = np.arange(sad.shape[0], dtype=np.int32) + (sy0 - y0)
            dxs = np.arange(sad.shape[1], dtype=np.int32) + (sx0 - x0)
            score = sad + config.flow_smooth * np.hypot(dys[:, None], dxs[None, :])
            flat = score.ravel()
            best_i = int(np.argmin(flat))
            best = float(flat[best_i])
            if flat.size < 2:
                second = float("inf")
            else:
                flat[best_i] = np.inf
                second = float(flat.min())
            bj, bi = np.unravel_index(best_i, score.shape)
            u[j, i] = int(dxs[bi])
            v[j, i] = int(dys[bj])
            if second >= float("inf") - 1:
                peak = 0.0
            else:
                ratio = best / (second + 1e-3)
                peak = max(0.0, 1.0 - ratio)
            conf[j, i] = float(peak * min(1.0, variance / (4.0 * config.texture_var)))
    return FlowField(u=u, v=v, confidence=conf, weak_texture=weak, xs=xs, ys=ys)


def reference_flow_loop(prev: np.ndarray, curr: np.ndarray, config: VisionConfig) -> FlowField:
    """Scalar SAD search. Kept as the numerical oracle for the vectorized path."""
    height, width = prev.shape
    nx, ny = config.flow_nx, config.flow_ny
    block, search = config.flow_block, config.flow_search
    half = block // 2
    u = np.zeros((ny, nx), dtype=np.float32)
    v = np.zeros((ny, nx), dtype=np.float32)
    conf = np.zeros((ny, nx), dtype=np.float32)
    weak = np.zeros((ny, nx), dtype=bool)
    xs = np.zeros((ny, nx), dtype=np.float32)
    ys = np.zeros((ny, nx), dtype=np.float32)
    for j in range(ny):
        cy = int((j + 0.5) * height / ny)
        for i in range(nx):
            cx = int((i + 0.5) * width / nx)
            xs[j, i] = cx
            ys[j, i] = cy
            y0, x0 = cy - half, cx - half
            y1, x1 = y0 + block, x0 + block
            if y0 < 0 or x0 < 0 or y1 > height or x1 > width:
                weak[j, i] = True
                continue
            templ = prev[y0:y1, x0:x1].astype(np.int16)
            variance = float(templ.var())
            if variance < config.texture_var:
                weak[j, i] = True
                continue
            best = float("inf")
            second = float("inf")
            bu = bv = 0
            for dy in range(-search, search + 1):
                yy0, yy1 = y0 + dy, y1 + dy
                if yy0 < 0 or yy1 > height:
                    continue
                for dx in range(-search, search + 1):
                    xx0, xx1 = x0 + dx, x1 + dx
                    if xx0 < 0 or xx1 > width:
                        continue
                    patch = curr[yy0:yy1, xx0:xx1].astype(np.int16)
                    sad = float(np.mean(np.abs(patch - templ)))
                    score = sad + config.flow_smooth * hypot(dx, dy)
                    if score < best:
                        second = best
                        best = score
                        bu, bv = dx, dy
                    elif score < second:
                        second = score
            u[j, i] = bu
            v[j, i] = bv
            if second >= float("inf") - 1:
                peak = 0.0
            else:
                ratio = best / (second + 1e-3)
                peak = max(0.0, 1.0 - ratio)
            conf[j, i] = float(peak * min(1.0, variance / (4.0 * config.texture_var)))
    return FlowField(u=u, v=v, confidence=conf, weak_texture=weak, xs=xs, ys=ys)


def expansion(field: FlowField) -> float:
    """Radial residual of the block field. Prefer scale_expansion for approach."""
    valid = (~field.weak_texture) & (field.confidence > 0.08)
    if int(valid.sum()) < 3:
        return 0.0
    cx = float(field.xs.mean())
    cy = float(field.ys.mean())
    dx = field.xs - cx
    dy = field.ys - cy
    radius = np.sqrt(dx * dx + dy * dy) + 1e-3
    radial = (field.u * dx + field.v * dy) / radius
    return float(radial[valid].mean())


def mean_flow(field: FlowField) -> tuple[float, float, float]:
    valid = (~field.weak_texture) & (field.confidence > 0.08)
    if int(valid.sum()) == 0:
        return 0.0, 0.0, 0.0
    moving = valid & (np.hypot(field.u, field.v) >= 1.0)
    use = moving if int(moving.sum()) >= max(3, int(0.25 * valid.sum())) else valid
    return (
        float(np.median(field.u[use])),
        float(np.median(field.v[use])),
        float(field.confidence[valid].mean()),
    )


def scale_expansion(prev: np.ndarray, curr: np.ndarray, min_conf: float = 0.10) -> tuple[float, float]:
    """Fractional scale: positive when curr looks like a zoom-in of prev (approach)."""
    scales = (0.90, 0.94, 0.98, 1.0, 1.04, 1.08, 1.12, 1.16)
    scores: list[tuple[float, float]] = []
    for scale in scales:
        if scale >= 1.0:
            warped = _zoom_gray(prev, scale)
            sad = _inner_sad(warped, curr)
        else:
            warped = _zoom_gray(curr, 1.0 / scale)
            sad = _inner_sad(warped, prev)
        scores.append((sad, scale))
    scores.sort()
    best_sad, best_scale = scores[0]
    second_sad = scores[1][0]
    peak = max(0.0, 1.0 - best_sad / (second_sad + 1e-3))
    delta = float(best_scale - 1.0)
    if peak < min_conf:
        return 0.0, float(peak)
    return delta, float(peak)


def _zoom_gray(gray: np.ndarray, factor: float) -> np.ndarray:
    height, width = gray.shape
    if abs(factor - 1.0) < 1e-6:
        return gray
    nh = min(height, max(4, int(round(height / factor))))
    nw = min(width, max(4, int(round(width / factor))))
    y0, x0 = (height - nh) // 2, (width - nw) // 2
    crop = gray[y0 : y0 + nh, x0 : x0 + nw]
    ys = np.linspace(0, crop.shape[0] - 1, height).astype(np.int32)
    xs = np.linspace(0, crop.shape[1] - 1, width).astype(np.int32)
    return crop[ys][:, xs]


def _inner_sad(a: np.ndarray, b: np.ndarray) -> float:
    h, w = a.shape
    y0, x0 = h // 6, w // 6
    aa = a[y0 : h - y0, x0 : w - x0].astype(np.float32)
    bb = b[y0 : h - y0, x0 : w - x0].astype(np.float32)
    return float(np.mean(np.abs(aa - bb)))


def residual_objectness(field: FlowField, mean_u: float, mean_v: float, exp: float) -> float:
    """Flow leftover after a uniform (camera-like) and radial (body-like) model."""
    valid = (~field.weak_texture) & (field.confidence > 0.08)
    if int(valid.sum()) < 3:
        return 0.0
    cx = float(field.xs.mean())
    cy = float(field.ys.mean())
    dx = field.xs - cx
    dy = field.ys - cy
    radius = np.sqrt(dx * dx + dy * dy) + 1e-3
    pred_u = mean_u + exp * dx / radius
    pred_v = mean_v + exp * dy / radius
    err = np.hypot(field.u - pred_u, field.v - pred_v)
    return float(err[valid].mean())
