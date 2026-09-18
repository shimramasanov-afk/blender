from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class NormRect:
    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        for name, value in (("x", self.x), ("y", self.y), ("w", self.w), ("h", self.h)):
            if value < 0 or value > 1:
                raise ValueError(f"{name} must be in [0, 1], got {value}")

    def pixel_box(self, width: int, height: int) -> tuple[int, int, int, int]:
        x0 = int(self.x * width)
        y0 = int(self.y * height)
        x1 = min(width, x0 + int(self.w * width))
        y1 = min(height, y0 + int(self.h * height))
        return x0, y0, x1, y1

    @property
    def empty(self) -> bool:
        return self.w <= 0 or self.h <= 0

    @classmethod
    def from_pixel_box(
        cls, x0: int, y0: int, x1: int, y1: int, width: int, height: int
    ) -> "NormRect":
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        if x1 <= x0 or y1 <= y0:
            raise ValueError("pixel box must have positive area")
        rect = cls(x0 / width, y0 / height, (x1 - x0) / width, (y1 - y0) / height)
        if rect.pixel_box(width, height) != (x0, y0, x1, y1):
            raise ValueError("pixel box does not survive normalization")
        return rect


@dataclass(frozen=True, slots=True)
class MaskSpec:
    name: str
    rect: NormRect


@dataclass(frozen=True, slots=True)
class WindowProfile:
    """Per-window ROI and named masks. No game HUD pixels in the capture module."""

    profile_id: str
    roi: NormRect
    masks: tuple[MaskSpec, ...]
    mask_fill: tuple[int, int, int] = (0, 0, 0)

    @classmethod
    def generic(cls) -> WindowProfile:
        return cls(
            profile_id="generic",
            roi=NormRect(0.0, 0.0, 1.0, 1.0),
            masks=(),
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> WindowProfile:
        roi_raw = data.get("roi") or {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}
        masks = []
        for item in data.get("masks") or ():
            rect = NormRect(*_rect_tuple(item["norm_rect"]))
            if not rect.empty:
                masks.append(MaskSpec(name=str(item["name"]), rect=rect))
        fill = tuple(int(v) for v in (data.get("mask_fill") or (0, 0, 0)))
        if len(fill) != 3:
            raise ValueError("mask_fill must be RGB")
        return cls(
            profile_id=str(data.get("profile_id") or "generic"),
            roi=NormRect(float(roi_raw["x"]), float(roi_raw["y"]), float(roi_raw["w"]), float(roi_raw["h"])),
            masks=tuple(masks),
            mask_fill=(fill[0], fill[1], fill[2]),
        )

    @classmethod
    def load(cls, path: Path | None) -> WindowProfile:
        if path is None:
            return cls.generic()
        return cls.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def _rect_tuple(values: list[float] | tuple[float, ...]) -> tuple[float, float, float, float]:
    if len(values) != 4:
        raise ValueError("norm_rect must be [x, y, w, h]")
    return float(values[0]), float(values[1]), float(values[2]), float(values[3])
