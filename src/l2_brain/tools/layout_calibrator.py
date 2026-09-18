"""Draw fixed UI slot boxes on a frame. No HID. Not Frozen L1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.capture.helper import list_windows, resolve_helper
from l2_brain.vision.calibrate_hud import grab_window_frame, read_png, resolve_parallels_window, write_png
from l2_brain.vision.layout_slots import DEFAULT_PROFILE, LayoutSlots

SLOT_COLORS: dict[str, tuple[int, int, int]] = {
    "hud_self": (0, 220, 80),
    "hud_target": (240, 40, 40),
    "radar": (255, 170, 40),
    "slot_dialog_left": (40, 110, 255),
    "slot_modal_right": (200, 40, 220),
    "hotbar": (250, 230, 40),
}
SLOT_LABELS: dict[str, str] = {
    "hud_self": "HUD SELF",
    "hud_target": "HUD TARGET",
    "radar": "RADAR",
    "slot_dialog_left": "SLOT A DIALOG",
    "slot_modal_right": "SLOT B MODAL",
    "hotbar": "HOTBAR F1-F12",
}

_FONT: dict[str, tuple[str, ...]] = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
}


def draw_layout_overlay(image: np.ndarray, slots: LayoutSlots) -> np.ndarray:
    out = np.ascontiguousarray(image[:, :, :3], dtype=np.uint8).copy()
    height, width = out.shape[:2]
    for name, slot in slots.slots.items():
        color = SLOT_COLORS.get(name, (220, 220, 220))
        box = slots.box_on_frame(name, width, height)
        _blend_box(out, box, color, alpha=0.28)
        _stroke_box(out, box, color)
        label = SLOT_LABELS.get(name, name.upper())
        _draw_label(out, box[0] + 6, box[1] + 6, label, color)
        _ = slot
    return out


def run_layout_grid(
    *,
    save_path: Path,
    window_id: int | None = None,
    profile_path: Path = DEFAULT_PROFILE,
    image_path: Path | None = None,
) -> dict[str, Any]:
    slots = LayoutSlots.load(profile_path)
    if image_path is not None:
        image = read_png(image_path)
        source = str(image_path)
        wid = window_id
    else:
        helper = resolve_helper(build=False)
        catalog = list_windows(helper)
        resolved = None
        if window_id is not None:
            for row in catalog.get("windows") or []:
                if int(row.get("id") or 0) == int(window_id):
                    resolved = row
                    break
        if resolved is None:
            resolved = resolve_parallels_window(list(catalog.get("windows") or []))
        if resolved is None or not resolved.get("on_screen"):
            return {
                "ok": False,
                "reason": "window_not_on_screen",
                "hid_sent": False,
                "window_id": int((resolved or {}).get("id") or 0) or window_id,
                "on_screen": bool((resolved or {}).get("on_screen")),
            }
        wid = int(resolved["id"])
        image = grab_window_frame(wid)
        source = "sck"
    overlay = draw_layout_overlay(image, slots)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    write_png(save_path, overlay)
    height, width = overlay.shape[:2]
    boxes = {name: list(slots.box_on_frame(name, width, height)) for name in slots.slots}
    return {
        "ok": True,
        "hid_sent": False,
        "farm": False,
        "png": str(save_path),
        "source": source,
        "window_id": wid,
        "width": width,
        "height": height,
        "ref_window": list(slots.ref_window),
        "slot_boxes": boxes,
        "slot_a": boxes.get("slot_dialog_left"),
        "slot_b": boxes.get("slot_modal_right"),
    }


def _blend_box(
    image: np.ndarray,
    box: tuple[int, int, int, int],
    color: tuple[int, int, int],
    *,
    alpha: float,
) -> None:
    x0, y0, x1, y1 = _clip_box(box, image.shape[1], image.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    crop = image[y0:y1, x0:x1]
    tint = np.full_like(crop, color)
    image[y0:y1, x0:x1] = np.clip(crop.astype(np.float32) * (1.0 - alpha) + tint.astype(np.float32) * alpha, 0, 255).astype(
        np.uint8
    )


def _stroke_box(image: np.ndarray, box: tuple[int, int, int, int], color: tuple[int, int, int]) -> None:
    x0, y0, x1, y1 = _clip_box(box, image.shape[1], image.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    image[y0 : min(y0 + 3, y1), x0:x1] = color
    image[max(y1 - 3, y0) : y1, x0:x1] = color
    image[y0:y1, x0 : min(x0 + 3, x1)] = color
    image[y0:y1, max(x1 - 3, x0) : x1] = color


def _draw_label(image: np.ndarray, x: int, y: int, text: str, color: tuple[int, int, int]) -> None:
    scale = 2 if image.shape[0] >= 800 else 1
    cursor = x
    for ch in text.upper():
        glyph = _FONT.get(ch, _FONT[" "])
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit != "1":
                    continue
                yy0 = y + row * scale
                xx0 = cursor + col * scale
                image[yy0 : yy0 + scale, xx0 : xx0 + scale] = color
        cursor += 6 * scale


def _clip_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return max(0, x0), max(0, y0), min(width, x1), min(height, y1)
