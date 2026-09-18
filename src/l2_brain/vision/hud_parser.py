"""Classic HUD bars from pixels. No process memory. No packets. No policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.capture.profile import NormRect

BLACK_MEAN = 4.0
BLACK_MAX = 12.0
COLUMN_ON = 0.25
LEADING_EMPTY_MAX = 0.15
SHIFT_SEARCH_X1 = 0.18
SHIFT_SEARCH_Y0 = 0.03
SHIFT_SEARCH_Y1 = 0.16
SHIFT_ROW_ON = 0.18
TARGET_SEARCH_X0 = 0.00
TARGET_SEARCH_X1 = 0.82
TARGET_SEARCH_Y0 = 0.02
TARGET_SEARCH_Y1 = 0.22
TARGET_BAND_MIN_W = 80
TARGET_BAND_MAX_H = 28
ENGAGE_HP_MIN = 0.15

ColorRange = tuple[tuple[int, int, int], tuple[int, int, int]]

HP_RED: ColorRange = ((130, 0, 0), (255, 90, 90))
MP_BLUE: ColorRange = ((0, 0, 140), (90, 130, 255))
CP_YELLOW: ColorRange = ((150, 110, 0), (255, 220, 90))
PLATE_BROWN: ColorRange = ((30, 20, 15), (90, 70, 55))
PLATE_BROWN_MIN = 0.12
PLATE_GROOVE_MIN = 0.20
PLATE_RED_MIN = 0.08
EMPTY_PLATE_STD_MIN = 8.0
SLOT_READY_LUMA_MIN = 55.0
SLOT_READY_SAT_MIN = 22.0

PRESETS: dict[str, ColorRange] = {
    "hp_red": HP_RED,
    "mp_blue": MP_BLUE,
    "cp_yellow": CP_YELLOW,
}


@dataclass(frozen=True, slots=True)
class HudLayout:
    self_bars: NormRect
    target_frame: NormRect
    self_hp: NormRect | None = None
    self_mp: NormRect | None = None
    self_cp: NormRect | None = None
    target_hp: NormRect | None = None
    hotbar_f1: NormRect | None = None
    hotbar_f2: NormRect | None = None
    hotbar_f3: NormRect | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> HudLayout:
        hud = data.get("hud") or {}
        if not hud:
            hud = {item["name"]: item for item in (data.get("masks") or ()) if "name" in item}
        return cls(
            self_bars=_require_rect(hud, "self_bars"),
            target_frame=_require_rect(hud, "target_frame"),
            self_hp=_optional_rect(hud, "self_hp"),
            self_mp=_optional_rect(hud, "self_mp"),
            self_cp=_optional_rect(hud, "self_cp"),
            target_hp=_optional_rect(hud, "target_hp"),
            hotbar_f1=_optional_rect(hud, "hotbar_f1"),
            hotbar_f2=_optional_rect(hud, "hotbar_f2"),
            hotbar_f3=_optional_rect(hud, "hotbar_f3"),
        )

    @classmethod
    def load(cls, path: Path) -> HudLayout:
        return cls.from_mapping(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class HUDParseResult:
    valid: bool
    confidence: float
    self_hp_ratio: float | None
    self_mp_ratio: float | None
    self_cp_ratio: float | None
    target_locked: bool
    target_hp_ratio: float | None
    target_dead: bool = False
    slot_f1_ready: bool | None = None
    slot_f2_ready: bool | None = None
    slot_f3_ready: bool | None = None
    reason: str | None = None


def extract_bar_ratio(
    image_crop: np.ndarray,
    color_range_hsv_or_rgb: ColorRange | str,
    *,
    column_threshold: float = COLUMN_ON,
) -> float:
    """Left-aligned fill fraction in [0, 1] from a continuous column profile."""
    crop = _as_rgb(image_crop)
    if crop is None or crop.size == 0 or crop.shape[0] < 1 or crop.shape[1] < 1:
        return 0.0
    low, high = _resolve_range(color_range_hsv_or_rgb)
    mask = _in_range(crop, low, high)
    scores = mask.mean(axis=0)
    on = scores >= column_threshold
    width = int(on.shape[0])
    if width == 0 or not bool(on.any()):
        return 0.0
    start = 0
    while start < width and not on[start]:
        start += 1
    if start / width > LEADING_EMPTY_MAX:
        return 0.0
    end = start
    while end < width and on[end]:
        end += 1
    return float(end / width)


class HUDParser:
    def __init__(self, layout: HudLayout) -> None:
        self.layout = layout

    @classmethod
    def from_profile(cls, path: Path) -> HUDParser:
        return cls(HudLayout.load(path))

    def parse(self, image: np.ndarray) -> HUDParseResult:
        rgb = _as_rgb(image)
        if rgb is None:
            return _invalid("empty_or_bad_shape")
        if rgb.shape[0] < 8 or rgb.shape[1] < 8:
            return _invalid("too_small")
        if float(rgb.mean()) < BLACK_MEAN and float(rgb.max()) < BLACK_MAX:
            return _invalid("black_or_folded")
        height, width = rgb.shape[:2]
        bars = _crop(rgb, self.layout.self_bars, width, height)
        frame = _crop(rgb, self.layout.target_frame, width, height)
        if bars.size == 0 or frame.size == 0:
            return _invalid("empty_roi")
        hp_crop = _named_or_band(rgb, self.layout.self_hp, bars, 1, 3, width, height)
        mp_crop = _named_or_band(rgb, self.layout.self_mp, bars, 2, 3, width, height)
        cp_crop = _named_or_band(rgb, self.layout.self_cp, bars, 0, 3, width, height)
        hp = _named_ratio(hp_crop, HP_RED)
        mp = _named_ratio(mp_crop, MP_BLUE)
        cp = _named_ratio(cp_crop, CP_YELLOW)
        recovered = recover_self_bar_ratios(rgb)
        if recovered is not None and _named_self_is_sliver(hp_crop, hp, recovered[0]):
            hp, mp, cp = recovered
        thp = _crop(rgb, self.layout.target_hp, width, height) if self.layout.target_hp else _band(frame, 1, 2)
        locked = detect_target_plate(frame, thp if thp.size else None)
        target_hp = _named_ratio(thp, HP_RED) if locked and thp.size else None
        if (not locked) or (target_hp is None) or (target_hp < ENGAGE_HP_MIN):
            recovered = recover_target_lock(rgb, exclude=_self_exclude_box(rgb, self.layout))
            if recovered is not None:
                locked, target_hp = recovered
        if locked and target_hp is None:
            target_hp = 0.0
        dead = bool(locked and target_hp == 0.0)
        return HUDParseResult(
            valid=True,
            confidence=_confidence(hp_crop, HP_RED, locked, frame),
            self_hp_ratio=hp,
            self_mp_ratio=mp,
            self_cp_ratio=cp,
            target_locked=locked,
            target_hp_ratio=target_hp,
            target_dead=dead,
            slot_f1_ready=_slot_flag(rgb, self.layout.hotbar_f1, width, height),
            slot_f2_ready=_slot_flag(rgb, self.layout.hotbar_f2, width, height),
            slot_f3_ready=_slot_flag(rgb, self.layout.hotbar_f3, width, height),
        )


def _require_rect(hud: dict[str, Any], name: str) -> NormRect:
    item = hud.get(name)
    if item is None:
        raise ValueError(f"hud.{name} is required")
    return NormRect(*_rect_tuple(item.get("norm_rect") or item))


def _optional_rect(hud: dict[str, Any], name: str) -> NormRect | None:
    item = hud.get(name)
    if item is None:
        return None
    rect = NormRect(*_rect_tuple(item.get("norm_rect") or item))
    return None if rect.empty else rect


def _rect_tuple(values: list[float] | tuple[float, ...]) -> tuple[float, float, float, float]:
    if len(values) != 4:
        raise ValueError("norm_rect must be [x, y, w, h]")
    return float(values[0]), float(values[1]), float(values[2]), float(values[3])


def _as_rgb(image: np.ndarray | None) -> np.ndarray | None:
    if image is None:
        return None
    arr = np.asarray(image)
    if arr.ndim != 3 or arr.shape[2] not in (3, 4):
        return None
    if arr.shape[2] == 4:
        arr = arr[:, :, :3]
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(arr)


def _resolve_range(spec: ColorRange | str) -> ColorRange:
    if isinstance(spec, str):
        if spec not in PRESETS:
            raise ValueError(f"unknown color preset: {spec}")
        return PRESETS[spec]
    return spec


def _in_range(crop: np.ndarray, low: tuple[int, int, int], high: tuple[int, int, int]) -> np.ndarray:
    lo = np.array(low, dtype=np.uint8)
    hi = np.array(high, dtype=np.uint8)
    return np.all((crop >= lo) & (crop <= hi), axis=2)


def _crop(image: np.ndarray, rect: NormRect | None, width: int, height: int) -> np.ndarray:
    if rect is None or rect.empty:
        return image[0:0, 0:0]
    x0, y0, x1, y1 = rect.pixel_box(width, height)
    if x1 <= x0 or y1 <= y0:
        return image[0:0, 0:0]
    return image[y0:y1, x0:x1]


def _band(crop: np.ndarray, index: int, parts: int) -> np.ndarray:
    if crop.size == 0 or parts < 1:
        return crop
    h = crop.shape[0]
    y0 = (h * index) // parts
    y1 = (h * (index + 1)) // parts
    return crop[y0:y1, :]


def _named_or_band(
    image: np.ndarray,
    rect: NormRect | None,
    parent: np.ndarray,
    index: int,
    parts: int,
    width: int,
    height: int,
) -> np.ndarray:
    if rect is not None:
        return _crop(image, rect, width, height)
    return _band(parent, index, parts)


def is_slot_ready(crop_slot: np.ndarray) -> bool:
    """Classic hotbar: bright saturated icon is ready; dim/grey mask is cooldown."""
    rgb = _as_rgb(crop_slot)
    if rgb is None or rgb.size == 0:
        return False
    luma = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    sat = rgb.max(axis=2).astype(np.float32) - rgb.min(axis=2).astype(np.float32)
    return float(luma.mean()) >= SLOT_READY_LUMA_MIN and float(sat.mean()) >= SLOT_READY_SAT_MIN


def _slot_flag(image: np.ndarray, rect: NormRect | None, width: int, height: int) -> bool | None:
    if rect is None or rect.empty:
        return None
    crop = _crop(image, rect, width, height)
    if crop.size == 0:
        return None
    return is_slot_ready(crop)


def recover_self_bar_ratios(image: np.ndarray) -> tuple[float, float, float] | None:
    """Find CP/HP/MP if the status window moved out of the parked named ROI."""
    rgb = _as_rgb(image)
    if rgb is None or rgb.size == 0:
        return None
    height, width = rgb.shape[:2]
    x_right = max(8, int(SHIFT_SEARCH_X1 * width))
    y0 = int(SHIFT_SEARCH_Y0 * height)
    y1 = max(y0 + 8, int(SHIFT_SEARCH_Y1 * height))
    crop = rgb[y0:y1, 0:x_right]
    boxes = [
        box
        for box in (
            _color_band_box(crop, HP_RED),
            _color_band_box(crop, MP_BLUE),
            _color_band_box(crop, CP_YELLOW),
        )
        if box is not None
    ]
    if not boxes:
        return None
    aligned = _aligned_bar_x(boxes)
    if aligned is None:
        return None
    x0 = max(0, aligned[0] - 2)
    x1 = min(crop.shape[1], aligned[1] + 2)
    hp = _ratio_in_box(crop, HP_RED, x0, x1)
    mp = _ratio_in_box(crop, MP_BLUE, x0, x1)
    cp = _ratio_in_box(crop, CP_YELLOW, x0, x1)
    if hp == 0.0 and mp == 0.0 and cp == 0.0:
        return None
    return hp, mp, cp


def _color_band_box(crop: np.ndarray, color_range: ColorRange) -> tuple[int, int, int, int] | None:
    rgb = _as_rgb(crop)
    if rgb is None or rgb.size == 0:
        return None
    mask = _in_range(rgb, *color_range)
    rows = np.where(mask.mean(axis=1) >= SHIFT_ROW_ON)[0]
    if rows.size == 0:
        return None
    sub = mask[int(rows[0]) : int(rows[-1]) + 1]
    cols = np.where(sub.any(axis=0))[0]
    if cols.size == 0:
        return None
    splits = np.where(np.diff(cols) > 8)[0]
    starts = np.concatenate(([0], splits + 1))
    ends = np.concatenate((splits, [cols.size - 1]))
    best = 0
    bx0 = int(cols[0])
    bx1 = int(cols[-1]) + 1
    for start, end in zip(starts, ends):
        x0 = int(cols[int(start)])
        x1 = int(cols[int(end)]) + 1
        if x1 - x0 > best:
            best = x1 - x0
            bx0, bx1 = x0, x1
    return int(rows[0]), int(rows[-1]) + 1, bx0, bx1


def _ratio_in_box(crop: np.ndarray, color_range: ColorRange, x0: int, x1: int) -> float:
    box = _color_band_box(crop, color_range)
    if box is None or x1 <= x0:
        return 0.0
    y0, y1, _cx0, _cx1 = box
    band = crop[y0:y1, x0:x1]
    rgb = _as_rgb(band)
    if rgb is None or rgb.size == 0:
        return 0.0
    on = _in_range(rgb, *color_range).any(axis=0)
    idx = np.where(on)[0]
    if idx.size == 0:
        return 0.0
    first = int(idx[0])
    last = int(idx[-1])
    width = int(on.shape[0])
    if width < 1 or first / width > LEADING_EMPTY_MAX:
        return 0.0
    span = on[first : last + 1]
    if float(span.mean()) >= 0.70:
        return float((last + 1) / width)
    return extract_bar_ratio(band, color_range)


def recover_target_lock(
    image: np.ndarray,
    exclude: tuple[int, int, int, int] | None = None,
) -> tuple[bool, float] | None:
    """Find a target plate+HP bar if the widget left the parked center ROI."""
    rgb = _as_rgb(image)
    if rgb is None or rgb.size == 0:
        return None
    height, width = rgb.shape[:2]
    if width < 1000 or height < 400:
        return None
    x0 = int(TARGET_SEARCH_X0 * width)
    x1 = max(x0 + TARGET_BAND_MIN_W, int(TARGET_SEARCH_X1 * width))
    y0 = int(TARGET_SEARCH_Y0 * height)
    y1 = max(y0 + 8, int(TARGET_SEARCH_Y1 * height))
    crop = rgb[y0:y1, x0:x1]
    self_box = exclude
    for by0, by1, bx0, bx1 in _color_band_boxes(crop, HP_RED):
        if (bx1 - bx0) < TARGET_BAND_MIN_W or (by1 - by0) > TARGET_BAND_MAX_H:
            continue
        full = (x0 + bx0, y0 + by0, x0 + bx1, y0 + by1)
        if self_box is not None and _overlaps(full, self_box, pad=8):
            continue
        pad = 24
        plate = crop[
            max(0, by0 - pad) : min(crop.shape[0], by1 + pad),
            max(0, bx0 - 12) : min(crop.shape[1], bx1 + 12),
        ]
        hp_band = crop[by0:by1, bx0:bx1]
        ratio = _named_ratio(hp_band, HP_RED)
        plate_ok = detect_target_plate(plate, hp_band)
        if not plate_ok and ratio < ENGAGE_HP_MIN:
            continue
        if ratio < ENGAGE_HP_MIN:
            red = float(_in_range(hp_band, *HP_RED).mean())
            if red < PLATE_RED_MIN:
                continue
            ratio = ENGAGE_HP_MIN
        return True, float(ratio)
    return None


def _named_ratio(crop: np.ndarray, color_range: ColorRange) -> float:
    if crop.size == 0:
        return 0.0
    return _ratio_in_box(crop, color_range, 0, crop.shape[1])


def _aligned_bar_x(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int] | None:
    """Shared window of the largest overlapping CP/HP/MP cluster, not a stray bar."""
    if not boxes:
        return None
    best: tuple[int, int] | None = None
    best_score = -1
    for seed in boxes:
        members = [box for box in boxes if box[3] >= seed[2] and box[2] <= seed[3]]
        x0 = min(box[2] for box in members)
        x1 = max(box[3] for box in members)
        score = len(members) * 10000 + (x1 - x0)
        if score > best_score:
            best_score = score
            best = (x0, x1)
    return best


def _named_self_is_sliver(hp_crop: np.ndarray, named_hp: float, recovered_hp: float) -> bool:
    """Parked ROI missed or is much wider than the painted bar."""
    if recovered_hp <= named_hp + 0.15:
        return False
    if named_hp < 0.20:
        return True
    if hp_crop.size == 0 or hp_crop.shape[1] < 200:
        return False
    band = _color_band_box(hp_crop, HP_RED)
    if band is None:
        return True
    painted = band[3] - band[2]
    return painted / hp_crop.shape[1] < 0.55


def _self_exclude_box(image: np.ndarray, layout: HudLayout) -> tuple[int, int, int, int] | None:
    """Union of parked self widget and recovered CP/HP/MP bands."""
    rgb = _as_rgb(image)
    if rgb is None or rgb.size == 0:
        return None
    height, width = rgb.shape[:2]
    named = None
    if layout.self_bars is not None and not layout.self_bars.empty:
        named = layout.self_bars.pixel_box(width, height)
    x_right = max(8, int(SHIFT_SEARCH_X1 * width))
    y0 = int(SHIFT_SEARCH_Y0 * height)
    y1 = max(y0 + 8, int(SHIFT_SEARCH_Y1 * height))
    crop = rgb[y0:y1, 0:x_right]
    bands = [
        box
        for box in (
            _color_band_box(crop, HP_RED),
            _color_band_box(crop, MP_BLUE),
            _color_band_box(crop, CP_YELLOW),
        )
        if box is not None
    ]
    found = None
    if bands:
        found = (
            max(0, min(box[2] for box in bands) - 8),
            max(0, y0 + min(box[0] for box in bands) - 24),
            min(width, max(box[3] for box in bands) + 8),
            min(height, y0 + max(box[1] for box in bands) + 24),
        )
    if named is None:
        return found
    if found is None:
        return named
    return (
        min(named[0], found[0]),
        min(named[1], found[1]),
        max(named[2], found[2]),
        max(named[3], found[3]),
    )


def _color_band_boxes(crop: np.ndarray, color_range: ColorRange) -> list[tuple[int, int, int, int]]:
    rgb = _as_rgb(crop)
    if rgb is None or rgb.size == 0:
        return []
    mask = _in_range(rgb, *color_range)
    min_px = max(20, TARGET_BAND_MIN_W // 2)
    rows = np.where(mask.sum(axis=1) >= min_px)[0]
    if rows.size == 0:
        return []
    splits = np.where(np.diff(rows) > 2)[0]
    starts = np.concatenate(([0], splits + 1))
    ends = np.concatenate((splits, [rows.size - 1]))
    boxes: list[tuple[int, int, int, int]] = []
    for start, end in zip(starts, ends):
        y0 = int(rows[int(start)])
        y1 = int(rows[int(end)]) + 1
        cols = np.where(mask[y0:y1].any(axis=0))[0]
        if cols.size == 0:
            continue
        boxes.append((y0, y1, int(cols[0]), int(cols[-1]) + 1))
    return boxes


def _overlaps(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
    *,
    pad: int = 0,
) -> bool:
    return not (
        a[2] + pad <= b[0]
        or b[2] + pad <= a[0]
        or a[3] + pad <= b[1]
        or b[3] + pad <= a[1]
    )


def detect_target_plate(crop: np.ndarray, hp_crop: np.ndarray | None = None) -> bool:
    """Classic target chrome: dark brown plate / empty groove, not stone contrast."""
    frame = _as_rgb(crop)
    if frame is None or frame.size == 0:
        return False
    brown = float(_in_range(frame, *PLATE_BROWN).mean())
    groove = 0.0
    red = 0.0
    hp = _as_rgb(hp_crop) if hp_crop is not None else None
    if hp is not None and hp.size:
        groove = float(_in_range(hp, *PLATE_BROWN).mean())
        red = float(_in_range(hp, *HP_RED).mean())
    else:
        red = float(_in_range(frame, *HP_RED).mean())
    if red >= PLATE_RED_MIN:
        return True
    if groove < PLATE_GROOVE_MIN or brown < PLATE_BROWN_MIN:
        return False
    if frame.shape[1] >= 160 and float(frame.std()) < EMPTY_PLATE_STD_MIN:
        return False
    return True


def _target_present(frame: np.ndarray) -> bool:
    return detect_target_plate(frame)


def _confidence(hp_crop: np.ndarray, rng: ColorRange, locked: bool, frame: np.ndarray) -> float:
    if hp_crop.size == 0:
        return 0.2
    mask = _in_range(hp_crop, *rng)
    scores = mask.mean(axis=0)
    margin = float(np.mean(np.abs(scores - 0.5)))
    lock_term = 0.15 if locked else 0.0
    return float(min(1.0, 0.35 + margin + lock_term))


def _invalid(reason: str) -> HUDParseResult:
    return HUDParseResult(
        valid=False,
        confidence=0.0,
        self_hp_ratio=None,
        self_mp_ratio=None,
        self_cp_ratio=None,
        target_locked=False,
        target_hp_ratio=None,
        target_dead=False,
        reason=reason,
    )
