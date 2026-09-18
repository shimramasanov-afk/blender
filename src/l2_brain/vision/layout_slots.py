"""Fixed UI slot grid from the window profile. No OCR. Not Frozen L1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_PROFILE = Path("config/window_profiles/parallels_l2.json")


@dataclass(frozen=True, slots=True)
class LayoutSlot:
    name: str
    window_px: tuple[int, int, int, int]
    title_bar: tuple[int, int, int, int]
    hotkey_close: str = "escape"
    extra: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class LayoutSlots:
    ref_window: tuple[int, int]
    slots: dict[str, LayoutSlot]
    hotkey_close: str = "escape"

    def get(self, name: str) -> LayoutSlot:
        slot = self.slots.get(name)
        if slot is None:
            raise KeyError(f"unknown layout slot: {name}")
        return slot

    def box_on_frame(self, name: str, frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
        slot = self.get(name)
        sx = frame_w / max(self.ref_window[0], 1)
        sy = frame_h / max(self.ref_window[1], 1)
        x, y, w, h = slot.window_px
        x0 = int(round(x * sx))
        y0 = int(round(y * sy))
        x1 = min(frame_w, x0 + max(1, int(round(w * sx))))
        y1 = min(frame_h, y0 + max(1, int(round(h * sy))))
        return x0, y0, x1, y1

    def title_box_on_frame(self, name: str, frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
        slot = self.get(name)
        x0, y0, x1, y1 = self.box_on_frame(name, frame_w, frame_h)
        sx = (x1 - x0) / max(slot.window_px[2], 1)
        sy = (y1 - y0) / max(slot.window_px[3], 1)
        tx, ty, tw, th = slot.title_bar
        tx0 = x0 + int(round(tx * sx))
        ty0 = y0 + int(round(ty * sy))
        tx1 = min(x1, tx0 + max(1, int(round(tw * sx))))
        ty1 = min(y1, ty0 + max(1, int(round(th * sy))))
        return tx0, ty0, tx1, ty1

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> LayoutSlots:
        raw = data.get("layout_slots") or data
        ref = raw.get("ref_window") or [2056, 1290]
        ref_w, ref_h = int(ref[0]), int(ref[1])
        close = str(raw.get("hotkey_close") or "escape")
        slots: dict[str, LayoutSlot] = {}
        items = raw.get("slots") or raw
        for name, row in items.items():
            if name in {"ref_window", "hotkey_close", "slots"} or not isinstance(row, dict):
                continue
            px = row.get("window_px")
            if not px or len(px) != 4:
                continue
            title = row.get("title_bar") or [0, 0, int(px[2]), 30]
            extra = {k: v for k, v in row.items() if k not in {"window_px", "title_bar", "hotkey_close"}}
            slots[str(name)] = LayoutSlot(
                name=str(name),
                window_px=(int(px[0]), int(px[1]), int(px[2]), int(px[3])),
                title_bar=(int(title[0]), int(title[1]), int(title[2]), int(title[3])),
                hotkey_close=str(row.get("hotkey_close") or close),
                extra=extra or None,
            )
        return cls(ref_window=(ref_w, ref_h), slots=slots, hotkey_close=close)

    @classmethod
    def load(cls, path: Path | None = None) -> LayoutSlots:
        target = path or DEFAULT_PROFILE
        return cls.from_mapping(json.loads(target.read_text(encoding="utf-8")))
