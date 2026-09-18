"""Host click-through overlay for parking L2 windows. No HID. Not Frozen L1."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from l2_brain.capture.helper import list_windows, resolve_helper
from l2_brain.tools.layout_calibrator import SLOT_COLORS, SLOT_LABELS
from l2_brain.vision.calibrate_hud import resolve_parallels_window
from l2_brain.vision.layout_slots import DEFAULT_PROFILE, LayoutSlots

OVERLAY_NAME = "layout-overlay"


def slot_guides(
    slots: LayoutSlots,
    frame_w: int | None = None,
    frame_h: int | None = None,
) -> list[dict[str, Any]]:
    width = int(frame_w or slots.ref_window[0])
    height = int(frame_h or slots.ref_window[1])
    guides: list[dict[str, Any]] = []
    for name, slot in slots.slots.items():
        x0, y0, x1, y1 = slots.box_on_frame(name, width, height)
        red, green, blue = SLOT_COLORS.get(name, (220, 220, 220))
        guides.append(
            {
                "id": name,
                "name": SLOT_LABELS.get(name, name.upper()),
                "x": int(x0),
                "y": int(y0),
                "w": int(x1 - x0),
                "h": int(y1 - y0),
                "r": red / 255.0,
                "g": green / 255.0,
                "b": blue / 255.0,
            }
        )
        _ = slot
    return guides


def overlay_helper_path(root: Path | None = None) -> Path:
    here = root or Path(__file__).resolve().parents[3]
    return here / ".build" / OVERLAY_NAME


def overlay_source(root: Path | None = None) -> Path:
    here = root or Path(__file__).resolve().parents[3]
    return here / "macos" / "LayoutOverlay" / "main.swift"


def build_overlay_helper(root: Path | None = None) -> Path:
    dest = overlay_helper_path(root)
    source = overlay_source(root)
    if not source.is_file():
        raise FileNotFoundError(source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "swiftc",
            "-O",
            "-o",
            str(dest),
            str(source),
            "-framework",
            "AppKit",
            "-framework",
            "CoreGraphics",
            "-framework",
            "Foundation",
        ],
        check=True,
    )
    return dest


def resolve_overlay_helper(*, build: bool = True, root: Path | None = None) -> Path:
    dest = overlay_helper_path(root)
    source = overlay_source(root)
    if dest.is_file() and source.is_file() and dest.stat().st_mtime >= source.stat().st_mtime:
        return dest
    if not build:
        raise FileNotFoundError(dest)
    return build_overlay_helper(root)


def run_layout_overlay(
    *,
    window_id: int | None = None,
    profile_path: Path = DEFAULT_PROFILE,
    seconds: float = 180.0,
    show: bool = True,
    helper: Path | None = None,
) -> dict[str, Any]:
    slots = LayoutSlots.load(profile_path)
    guides = slot_guides(slots)
    payload: dict[str, Any] = {
        "ok": False,
        "hid_sent": False,
        "farm": False,
        "live_overlay": bool(show and seconds > 0),
        "seconds": float(seconds),
        "window_id": window_id,
        "slot_a": list(slots.get("slot_dialog_left").window_px) if "slot_dialog_left" in slots.slots else None,
        "slot_b": list(slots.get("slot_modal_right").window_px) if "slot_modal_right" in slots.slots else None,
        "ref_window": list(slots.ref_window),
        "guides": guides,
        "click_through": True,
    }
    helper_bin = resolve_helper(build=False)
    catalog = list_windows(helper_bin)
    resolved = None
    if window_id is not None:
        for row in catalog.get("windows") or []:
            if int(row.get("id") or 0) == int(window_id):
                resolved = row
                break
    if resolved is None:
        resolved = resolve_parallels_window(list(catalog.get("windows") or []))
    if resolved is None or not resolved.get("on_screen"):
        payload["reason"] = "window_not_on_screen"
        payload["on_screen"] = bool((resolved or {}).get("on_screen"))
        payload["window_id"] = int((resolved or {}).get("id") or 0) or window_id
        payload["shown"] = False
        return payload
    payload["window_id"] = int(resolved["id"])
    payload["window"] = {
        "x": resolved.get("x"),
        "y": resolved.get("y"),
        "width": resolved.get("width"),
        "height": resolved.get("height"),
        "on_screen": True,
    }
    host_w = int(resolved.get("width") or slots.ref_window[0])
    host_h = int(resolved.get("height") or slots.ref_window[1])
    guides = slot_guides(slots, host_w, host_h)
    payload["guides"] = guides
    payload["ref_window"] = list(slots.ref_window)
    payload["host_window"] = [host_w, host_h]
    if not show or seconds <= 0:
        payload["ok"] = True
        payload["shown"] = False
        return payload
    binary = helper or resolve_overlay_helper(build=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump({"slots": guides}, handle, ensure_ascii=False)
        json_path = Path(handle.name)
    proc = subprocess.Popen(
        [
            str(binary),
            "--window-id",
            str(int(resolved["id"])),
            "--seconds",
            str(float(seconds)),
            "--json",
            str(json_path),
        ]
    )
    payload["ok"] = True
    payload["shown"] = True
    payload["pid"] = proc.pid
    payload["json"] = str(json_path)
    return payload
