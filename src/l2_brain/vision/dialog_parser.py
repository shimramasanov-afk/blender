"""NPC HTML dialog from pixels. Left panel only. No OCR. No memory. No packets."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from l2_brain.capture.profile import NormRect

LEFT_PANEL = NormRect(0.05, 0.20, 0.37, 0.65)
PARCHMENT_ROI = NormRect(0.25, 0.20, 0.50, 0.55)
PARCHMENT_LUMA_MIN = 120.0
PARCHMENT_SCORE_MIN = 0.35
PANEL_LUMA_MAX = 95.0
PANEL_STD_MIN = 16.0
BLUE_LINK: tuple[tuple[int, int, int], tuple[int, int, int]] = ((15, 30, 120), (170, 210, 255))
GOLD_LINK: tuple[tuple[int, int, int], tuple[int, int, int]] = ((160, 110, 20), (255, 220, 100))
LINK_MIN_W = 40
LINK_MIN_H = 8
LINK_MAX_H = 25
LINK_ASPECT_MIN = 2.5
HTML_ITEMS_MIN = 2
REF_HEIGHT = 645.0


@dataclass(frozen=True, slots=True)
class DialogParseResult:
    open: bool
    confidence: float
    reason: str | None
    mean_luma: float
    parchment_score: float
    contrast_score: float
    first_link: tuple[int, int] | None
    link_kind: str | None
    links: tuple[tuple[int, int, str], ...] = ()


def extract_menu_items(frame: np.ndarray) -> list[tuple[int, int]]:
    """Centers of blue HTML links in the left panel, top to bottom."""
    rgb = _as_rgb(frame)
    if rgb is None:
        return []
    height, width = rgb.shape[:2]
    if height < 16 or width < 16:
        return []
    masked = np.zeros_like(rgb)
    x0, y0, x1, y1 = LEFT_PANEL.pixel_box(width, height)
    if x1 <= x0 or y1 <= y0:
        return []
    masked[y0:y1, x0:x1] = rgb[y0:y1, x0:x1]
    crop = masked[y0:y1, x0:x1]
    blue = np.all((crop >= BLUE_LINK[0]) & (crop <= BLUE_LINK[1]), axis=2)
    min_w, min_h, max_h = _geom_limits(height)
    boxes = _link_boxes(blue, min_w, min_h, max_h)
    items = [(x0 + (bx0 + bx1) // 2, y0 + (by0 + by1) // 2) for bx0, by0, bx1, by1 in boxes]
    items.sort(key=lambda row: row[1])
    return items


def is_dialog_open(frame: np.ndarray) -> bool:
    rgb = _as_rgb(frame)
    if rgb is None:
        return False
    items = extract_menu_items(rgb)
    return _left_panel_dark(rgb) and len(items) >= HTML_ITEMS_MIN


def parse_dialog(frame: np.ndarray) -> DialogParseResult:
    rgb = _as_rgb(frame)
    if rgb is None or rgb.shape[0] < 16 or rgb.shape[1] < 16:
        return DialogParseResult(False, 0.0, "too_small", 0.0, 0.0, 0.0, None, None, ())
    height, width = rgb.shape[:2]
    x0, y0, x1, y1 = LEFT_PANEL.pixel_box(width, height)
    crop = rgb[y0:y1, x0:x1]
    if crop.size == 0:
        return DialogParseResult(False, 0.0, "empty_roi", 0.0, 0.0, 0.0, None, None, ())
    luma = _luma(crop)
    mean_luma = float(luma.mean())
    contrast = _clip(float(luma.std()) / 80.0)
    items = extract_menu_items(rgb)
    links = tuple((x, y, "blue") for x, y in items)
    html_open = _left_panel_dark(rgb) and len(items) >= HTML_ITEMS_MIN
    parchment, p_mean = _parchment_score(rgb)
    parchment_open = parchment >= PARCHMENT_SCORE_MIN and p_mean >= PARCHMENT_LUMA_MIN
    opened = bool(html_open or parchment_open)
    if html_open:
        confidence = float(min(1.0, 0.50 + 0.08 * len(items) + 0.3 * contrast))
        reason = "html_links"
        first = items[0]
        kind = "blue"
    elif parchment_open:
        confidence = float(min(1.0, parchment))
        reason = "parchment"
        parch_link = _parchment_link(rgb)
        first = items[0] if items else parch_link
        kind = "blue" if items or parch_link is not None else "fallback_center"
        if first is None:
            first = (int((x0 + x1) / 2), int(y0 + 0.38 * (y1 - y0)))
        if not items:
            links = ((first[0], first[1], kind),)
    else:
        confidence = float(max(parchment, contrast))
        reason = "no_dialog"
        first = items[0] if items else None
        kind = "blue" if items else None
    return DialogParseResult(
        open=opened,
        confidence=confidence,
        reason=reason,
        mean_luma=mean_luma,
        parchment_score=float(parchment),
        contrast_score=contrast,
        first_link=first,
        link_kind=kind,
        links=links,
    )


def _left_panel_dark(rgb: np.ndarray) -> bool:
    height, width = rgb.shape[:2]
    x0, y0, x1, y1 = LEFT_PANEL.pixel_box(width, height)
    crop = rgb[y0:y1, x0:x1]
    if crop.size == 0:
        return False
    luma = _luma(crop)
    return float(luma.mean()) <= PANEL_LUMA_MAX and float(luma.std()) >= PANEL_STD_MIN


def _parchment_link(rgb: np.ndarray) -> tuple[int, int] | None:
    height, width = rgb.shape[:2]
    px0, py0, px1, py1 = PARCHMENT_ROI.pixel_box(width, height)
    crop = rgb[py0:py1, px0:px1]
    if crop.size == 0:
        return None
    mask = np.all((crop >= BLUE_LINK[0]) & (crop <= BLUE_LINK[1]), axis=2)
    ys, xs = np.nonzero(mask)
    if xs.size < 8:
        return None
    return (px0 + int(xs.mean()), py0 + int(ys.mean()))


def _parchment_score(rgb: np.ndarray) -> tuple[float, float]:
    height, width = rgb.shape[:2]
    px0, py0, px1, py1 = PARCHMENT_ROI.pixel_box(width, height)
    crop = rgb[py0:py1, px0:px1]
    if crop.size == 0:
        return 0.0, 0.0
    p_mean = float(_luma(crop).mean())
    r = float(crop[:, :, 0].mean())
    g = float(crop[:, :, 1].mean())
    b = float(crop[:, :, 2].mean())
    parchment = _clip((r - 40.0) / 180.0) * _clip((g - 30.0) / 180.0)
    parchment *= _clip((r - b) / 80.0) * _clip((p_mean - 90.0) / 80.0)
    return parchment, p_mean


def _geom_limits(height: int) -> tuple[int, int, int]:
    scale = max(1.0, float(height) / REF_HEIGHT)
    return (
        max(LINK_MIN_W, int(LINK_MIN_W * scale)),
        max(LINK_MIN_H, int(LINK_MIN_H * scale)),
        max(LINK_MAX_H, int(LINK_MAX_H * scale)),
    )


def _link_boxes(
    mask: np.ndarray,
    min_w: int,
    min_h: int,
    max_h: int,
) -> list[tuple[int, int, int, int]]:
    height, width = mask.shape
    min_pixels = max(8, min_w // 5)
    line_gap = max(3, min_h // 2)
    spans: list[tuple[int, int, int]] = []
    for y in range(height):
        xs = np.flatnonzero(mask[y])
        if xs.size < min_pixels:
            continue
        x_lo, x_hi = int(xs[0]), int(xs[-1]) + 1
        if x_hi - x_lo < min_w:
            continue
        spans.append((y, x_lo, x_hi))
    if not spans:
        return []
    groups: list[tuple[int, int, int, int]] = []
    y0, x0, x1 = spans[0][0], spans[0][1], spans[0][2]
    prev = spans[0][0]
    for y, lo, hi in spans[1:]:
        tall = (y - y0 + 1) > max_h
        if y - prev <= line_gap and abs(lo - x0) <= max(16, min_w // 3) and not tall:
            prev = y
            x0 = min(x0, lo)
            x1 = max(x1, hi)
        else:
            groups.append((x0, y0, x1, prev + 1))
            y0, prev, x0, x1 = y, y, lo, hi
    groups.append((x0, y0, x1, prev + 1))
    boxes: list[tuple[int, int, int, int]] = []
    for bx0, by0, bx1, by1 in groups:
        box_w = bx1 - bx0
        box_h = by1 - by0
        if box_w < min_w or box_h < min_h or box_h > max_h:
            continue
        if box_w / max(box_h, 1) < LINK_ASPECT_MIN:
            continue
        boxes.append((bx0, by0, bx1, by1))
    return boxes


def _luma(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]


def _as_rgb(image: np.ndarray | None) -> np.ndarray | None:
    if image is None:
        return None
    arr = np.asarray(image)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return None
    return np.ascontiguousarray(arr[:, :, :3])


def _clip(value: float) -> float:
    return float(min(1.0, max(0.0, value)))
