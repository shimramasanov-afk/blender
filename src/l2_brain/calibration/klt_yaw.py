"""Sparse KLT yaw plus coarse phase on the mid-plane. FOV degrees are assumed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.vision.preprocess import to_gray

WORK_X0, WORK_X1 = 0.15, 0.85
WORK_Y0, WORK_Y1 = 0.30, 0.70
CHAR_X0, CHAR_X1 = 0.34, 0.66
CHAR_Y0, CHAR_Y1 = 0.38, 1.00
HUD_BARS = (0.00, 0.00, 0.16, 0.14)
HUD_TARGET = (0.40, 0.00, 0.30, 0.12)
HUD_CHAT = (0.00, 0.72, 0.28, 0.28)
HUD_SHORTCUTS = (0.70, 0.82, 0.30, 0.18)

MAX_CORNERS = 200
QUALITY = 0.01
MIN_DISTANCE = 8
WIN = 15
LK_ITERS = 8
SEARCH = 80
SEARCH_STEP = 4
DY_MAX_PX = 16.0
RANSAC_THRESH_PX = 12.0
RANSAC_ITERS = 80
INLIER_RATIO_MIN = 0.70
INLIER_COUNT_MIN = 30
SHIFT_MIN_PX = 2.0
COARSE_W = 160
PIXEL_DIFF_MIN = 12.0
COARSE_PEAK_MIN = 0.04


def _work_slice(height: int, width: int) -> tuple[int, int, int, int]:
    y0, y1 = int(round(height * WORK_Y0)), int(round(height * WORK_Y1))
    x0, x1 = int(round(width * WORK_X0)), int(round(width * WORK_X1))
    return y0, y1, x0, x1


def work_band(image: np.ndarray) -> np.ndarray:
    gray = _as_gray_u8(image)
    y0, y1, x0, x1 = _work_slice(*gray.shape)
    return np.ascontiguousarray(gray[y0:y1, x0:x1])


def _masked_work(image: np.ndarray, profile_path: Path | None = None) -> tuple[np.ndarray, np.ndarray]:
    gray = _as_gray_u8(image)
    h, w = gray.shape
    y0, y1, x0, x1 = _work_slice(h, w)
    mask = analysis_mask(h, w, profile_path)[y0:y1, x0:x1]
    band = gray[y0:y1, x0:x1].astype(np.float64)
    band = np.where(mask, band, 0.0)
    return np.ascontiguousarray(band), np.ascontiguousarray(mask)


def _down_w(gray: np.ndarray, width: int) -> np.ndarray:
    h, w = gray.shape
    tw = max(16, int(width))
    th = max(8, int(round(h * tw / max(w, 1))))
    ys = np.linspace(0, h - 1, th).astype(np.int32)
    xs = np.linspace(0, w - 1, tw).astype(np.int32)
    return np.ascontiguousarray(gray[ys][:, xs].astype(np.float64))


def coarse_shift(
    prev: np.ndarray,
    curr: np.ndarray,
    profile_path: Path | None = None,
) -> dict[str, float]:
    """Phase + mean-abs on the mid-plane minus character/HUD. Sees large yaw; KLT ±40 px does not."""
    a, ma = _masked_work(prev, profile_path)
    b, mb = _masked_work(curr, profile_path)
    valid = ma & mb
    if a.size == 0 or b.size == 0 or a.shape != b.shape or int(valid.sum()) < 64:
        return {"coarse_dx": 0.0, "coarse_dy": 0.0, "coarse_peak": 0.0, "pixel_diff_mean": 0.0}
    diff = float(np.mean(np.abs(a[valid] - b[valid])))
    small_a = _down_w(a, COARSE_W)
    small_b = _down_w(b, COARSE_W)
    small_a -= float(small_a.mean())
    small_b -= float(small_b.mean())
    fa = np.fft.fft2(small_a)
    fb = np.fft.fft2(small_b)
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-12
    corr = np.fft.fftshift(np.fft.ifft2(cross).real)
    peak_ij = np.unravel_index(int(np.argmax(corr)), corr.shape)
    cy, cx = corr.shape[0] // 2, corr.shape[1] // 2
    dy = float(peak_ij[0] - cy)
    dx = float(peak_ij[1] - cx)
    peak = float(corr[int(peak_ij[0]), int(peak_ij[1])])
    scale = float(a.shape[1]) / float(small_a.shape[1])
    return {
        "coarse_dx": -dx * scale,
        "coarse_dy": -dy * (float(a.shape[0]) / float(small_a.shape[0])),
        "coarse_peak": peak,
        "pixel_diff_mean": diff,
    }


@dataclass(frozen=True, slots=True)
class KLTYaw:
    total_features: int
    tracked: int
    horizontal: int
    valid_inliers: int
    inlier_ratio: float
    median_dx: float
    std_dx: float
    median_dy: float
    reliable: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_features": self.total_features,
            "tracked": self.tracked,
            "horizontal": self.horizontal,
            "valid_inliers": self.valid_inliers,
            "inlier_ratio": self.inlier_ratio,
            "median_dx": self.median_dx,
            "std_dx": self.std_dx,
            "median_dy": self.median_dy,
            "reliable": self.reliable,
            "reason": self.reason,
            "algorithm": "klt_ransac",
        }


def _as_gray_u8(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        gray = to_gray(image)
    else:
        gray = np.asarray(image, dtype=np.float32)
    return np.clip(gray, 0, 255).astype(np.uint8)


def _fill_norm(mask: np.ndarray, x0: float, y0: float, x1: float, y1: float, value: bool) -> None:
    h, w = mask.shape
    xa = min(w, max(0, int(round(w * x0))))
    xb = min(w, max(xa, int(round(w * x1))))
    ya = min(h, max(0, int(round(h * y0))))
    yb = min(h, max(ya, int(round(h * y1))))
    mask[ya:yb, xa:xb] = value


def analysis_mask(height: int, width: int, profile_path: Path | None = None) -> np.ndarray:
    """Mid-plane minus character and HUD. True = usable."""
    mask = np.zeros((int(height), int(width)), dtype=bool)
    _fill_norm(mask, WORK_X0, WORK_Y0, WORK_X1, WORK_Y1, True)
    _fill_norm(mask, CHAR_X0, CHAR_Y0, CHAR_X1, CHAR_Y1, False)
    for x0, y0, w, h in (HUD_BARS, HUD_TARGET, HUD_CHAT, HUD_SHORTCUTS):
        _fill_norm(mask, x0, y0, x0 + w, y0 + h, False)
    if profile_path is not None and profile_path.is_file():
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        for item in data.get("masks") or ():
            rect = item.get("norm_rect") or ()
            if len(rect) == 4:
                x, y, ww, hh = (float(v) for v in rect)
                _fill_norm(mask, x, y, x + ww, y + hh, False)
        hud = data.get("hud") or {}
        for key in ("self_bars", "target_frame"):
            rect = (hud.get(key) or {}).get("norm_rect") or ()
            if len(rect) == 4:
                x, y, ww, hh = (float(v) for v in rect)
                _fill_norm(mask, x, y, x + ww, y + hh, False)
    return mask


def _box3(src: np.ndarray) -> np.ndarray:
    pad = np.pad(src, 1, mode="edge")
    return (
        pad[:-2, :-2]
        + pad[:-2, 1:-1]
        + pad[:-2, 2:]
        + pad[1:-1, :-2]
        + pad[1:-1, 1:-1]
        + pad[1:-1, 2:]
        + pad[2:, :-2]
        + pad[2:, 1:-1]
        + pad[2:, 2:]
    ) / 9.0


def _shi_tomasi(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    g = gray.astype(np.float32)
    gy, gx = np.gradient(g)
    ixx = _box3(gx * gx)
    iyy = _box3(gy * gy)
    ixy = _box3(gx * gy)
    trace = ixx + iyy
    diff = ixx - iyy
    min_eig = 0.5 * (trace - np.sqrt(np.maximum(diff * diff + 4.0 * ixy * ixy, 0.0)))
    min_eig = np.where(mask, min_eig, 0.0)
    peak = float(min_eig.max()) if min_eig.size else 0.0
    if peak < 1e-6:
        return np.zeros((0, 2), dtype=np.float32)
    keep = min_eig >= (QUALITY * peak)
    ys, xs = np.nonzero(keep)
    scores = min_eig[ys, xs]
    order = np.argsort(-scores)
    selected: list[tuple[float, float]] = []
    min_d2 = float(MIN_DISTANCE * MIN_DISTANCE)
    for idx in order:
        x = float(xs[idx])
        y = float(ys[idx])
        if any((x - px) * (x - px) + (y - py) * (y - py) < min_d2 for px, py in selected):
            continue
        selected.append((x, y))
        if len(selected) >= MAX_CORNERS:
            break
    if not selected:
        return np.zeros((0, 2), dtype=np.float32)
    return np.asarray(selected, dtype=np.float32)


def _window(image: np.ndarray, x: float, y: float, half: int) -> np.ndarray | None:
    xi = int(round(x))
    yi = int(round(y))
    if yi - half < 0 or xi - half < 0 or yi + half >= image.shape[0] or xi + half >= image.shape[1]:
        return None
    return image[yi - half : yi + half + 1, xi - half : xi + half + 1]


def _lk_one(
    prev: np.ndarray,
    curr: np.ndarray,
    gx: np.ndarray,
    gy: np.ndarray,
    x: float,
    y: float,
) -> tuple[float, float, bool]:
    half = WIN // 2
    px, py = float(x), float(y)
    for _ in range(LK_ITERS):
        a = _window(prev, px, py, half)
        ix = _window(gx, px, py, half)
        iy = _window(gy, px, py, half)
        b = _window(curr, px, py, half)
        if a is None or b is None or ix is None or iy is None:
            return px, py, False
        err = a.astype(np.float32) - b.astype(np.float32)
        ixv = ix.reshape(-1)
        iyv = iy.reshape(-1)
        ev = err.reshape(-1)
        gxx = float(np.dot(ixv, ixv))
        gyy = float(np.dot(iyv, iyv))
        gxy = float(np.dot(ixv, iyv))
        det = gxx * gyy - gxy * gxy
        if abs(det) < 1e-3:
            return px, py, False
        bx = float(np.dot(ixv, ev))
        by = float(np.dot(iyv, ev))
        dx = (gyy * bx - gxy * by) / det
        dy = (gxx * by - gxy * bx) / det
        px += dx
        py += dy
        if dx * dx + dy * dy < 0.01:
            break
    return px, py, True


def _track_points(prev: np.ndarray, curr: np.ndarray, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Integer SAD in ±SEARCH, then LK refine. Avoids periodic pyramid aliases."""
    if pts.size == 0:
        return np.zeros((0, 2), dtype=np.float32), np.zeros((0,), dtype=bool)
    prev_f = prev.astype(np.float32)
    curr_f = curr.astype(np.float32)
    gy, gx = np.gradient(prev_f)
    half = WIN // 2
    out = np.zeros((len(pts), 2), dtype=np.float32)
    ok = np.zeros((len(pts),), dtype=bool)
    for i, (x, y) in enumerate(pts):
        templ = _window(prev_f, float(x), float(y), half)
        if templ is None:
            out[i] = (x, y)
            continue
        best_dx, best_dy, best_sad = 0, 0, float("inf")
        for dy in range(-SEARCH, SEARCH + 1, SEARCH_STEP):
            for dx in range(-SEARCH, SEARCH + 1, SEARCH_STEP):
                patch = _window(curr_f, float(x) + dx, float(y) + dy, half)
                if patch is None:
                    continue
                sad = float(np.mean(np.abs(patch - templ)))
                if sad < best_sad:
                    best_dx, best_dy, best_sad = dx, dy, sad
        nx, ny, good = _lk_one(prev_f, curr_f, gx, gy, float(x) + best_dx, float(y) + best_dy)
        out[i] = (nx, ny)
        ok[i] = bool(good)
    return out, ok


def _try_cv2(
    prev_u8: np.ndarray,
    curr_u8: np.ndarray,
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int] | None:
    try:
        import cv2  # type: ignore
    except ImportError:
        return None
    corners = cv2.goodFeaturesToTrack(
        prev_u8,
        maxCorners=MAX_CORNERS,
        qualityLevel=QUALITY,
        minDistance=MIN_DISTANCE,
        mask=mask.astype(np.uint8) * 255,
    )
    if corners is None or len(corners) == 0:
        empty = np.zeros((0, 2), dtype=np.float32)
        return empty, empty, np.zeros((0,), dtype=bool), 0
    pts0 = corners.reshape(-1, 2).astype(np.float32)
    pts1, status, _err = cv2.calcOpticalFlowPyrLK(prev_u8, curr_u8, pts0, None)
    if pts1 is None or status is None:
        return pts0, pts0, np.zeros((len(pts0),), dtype=bool), len(pts0)
    return pts0, pts1.reshape(-1, 2), status.reshape(-1).astype(bool), len(pts0)


def _ransac_dx(dx: np.ndarray, *, rng: np.random.Generator) -> np.ndarray:
    if dx.size == 0:
        return np.zeros((0,), dtype=bool)
    if dx.size == 1:
        return np.ones((1,), dtype=bool)
    best = np.zeros(dx.shape, dtype=bool)
    for _ in range(RANSAC_ITERS):
        sample = float(dx[int(rng.integers(0, dx.size))])
        inl = np.abs(dx - sample) <= RANSAC_THRESH_PX
        if int(inl.sum()) > int(best.sum()):
            best = inl
    return best


def estimate_yaw_klt(
    prev: np.ndarray,
    curr: np.ndarray,
    *,
    profile_path: Path | None = None,
    seed: int = 0,
) -> KLTYaw:
    """median_dx > 0: features moved right (content)."""
    if prev.shape[:2] != curr.shape[:2]:
        raise ValueError("KLT frames must match")
    prev_u8 = _as_gray_u8(prev)
    curr_u8 = _as_gray_u8(curr)
    mask = analysis_mask(prev_u8.shape[0], prev_u8.shape[1], profile_path)
    cv = _try_cv2(prev_u8, curr_u8, mask)
    if cv is None:
        scale = 2 if prev_u8.shape[1] > 2000 else 1
        work_prev = prev_u8[::scale, ::scale]
        work_curr = curr_u8[::scale, ::scale]
        work_mask = mask[::scale, ::scale]
        pts0 = _shi_tomasi(work_prev, work_mask)
        pts1, ok = _track_points(work_prev, work_curr, pts0)
        if scale != 1 and pts0.size:
            pts0 = pts0 * float(scale)
            pts1 = pts1 * float(scale)
        total = int(len(pts0))
    else:
        pts0, pts1, ok, total = cv

    if total < 1 or pts0.size == 0:
        return KLTYaw(0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, False, "no_features")
    pts0 = np.asarray(pts0, dtype=np.float32).reshape(-1, 2)
    pts1 = np.asarray(pts1, dtype=np.float32).reshape(-1, 2)
    ok = np.asarray(ok, dtype=bool).reshape(-1)
    if len(pts1) != len(pts0):
        return KLTYaw(total, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, False, "track_shape")
    tracked = pts0[ok]
    moved = pts1[ok]
    n_tracked = int(len(tracked))
    if n_tracked < 1:
        return KLTYaw(total, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, False, "no_tracks")
    dxy = moved - tracked
    dx = dxy[:, 0]
    dy = dxy[:, 1]
    horiz = np.abs(dy) <= DY_MAX_PX
    dx_h = dx[horiz]
    n_h = int(dx_h.size)
    if n_h < 1:
        return KLTYaw(total, n_tracked, 0, 0, 0.0, 0.0, 0.0, float(np.median(dy)), False, "no_horizontal")
    rng = np.random.default_rng(seed)
    inl = _ransac_dx(dx_h, rng=rng)
    n_inl = int(inl.sum())
    ratio = float(n_inl / n_h) if n_h else 0.0
    dx_i = dx_h[inl] if n_inl else dx_h
    med = float(np.median(dx_i))
    std = float(np.std(dx_i)) if dx_i.size else 0.0
    med_dy = float(np.median(dy[horiz][inl])) if n_inl else float(np.median(dy[horiz]))
    reliable = bool(ratio >= INLIER_RATIO_MIN and n_inl >= INLIER_COUNT_MIN and abs(med) >= SHIFT_MIN_PX)
    reason = "ok" if reliable else "unreliable"
    if not reliable and n_inl < INLIER_COUNT_MIN:
        reason = "few_inliers"
    elif not reliable and ratio < INLIER_RATIO_MIN:
        reason = "low_inlier_ratio"
    elif not reliable and abs(med) < SHIFT_MIN_PX:
        reason = "shift_too_small"
    return KLTYaw(total, n_tracked, n_h, n_inl, ratio, med, std, med_dy, reliable, reason)
