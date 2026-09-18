"""Capture one window frame and draw HUD ROI. No HID. No policy."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.capture.helper import list_windows, resolve_helper
from l2_brain.capture.sck import SCKConfig, SCKFrameSource
from l2_brain.vision.hud_parser import HUDParser, HUDParseResult, HudLayout

ROI_COLORS: dict[str, tuple[int, int, int]] = {
    "self_bars": (0, 220, 80),
    "self_cp": (240, 200, 20),
    "self_hp": (240, 40, 40),
    "self_mp": (40, 80, 240),
    "target_frame": (20, 220, 220),
    "target_hp": (240, 40, 200),
    "hotbar_f1": (180, 255, 40),
    "hotbar_f2": (255, 160, 40),
    "hotbar_f3": (180, 80, 255),
}


def write_png(path: Path, image: np.ndarray) -> None:
    rgb = np.ascontiguousarray(image[:, :, :3], dtype=np.uint8)
    height, width = rgb.shape[:2]
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    payload = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def read_png(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    offset = 8
    width = height = bit_depth = color_type = interlace = None
    idat = bytearray()
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        tag = data[offset + 4 : offset + 8]
        chunk = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if tag == b"IHDR":
            width, height, bit_depth, color_type, _comp, _filter, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
        elif tag == b"IDAT":
            idat.extend(chunk)
        elif tag == b"IEND":
            break
    if width is None or height is None or bit_depth != 8 or interlace != 0:
        raise ValueError(f"unsupported PNG: {path}")
    raw = zlib.decompress(bytes(idat))
    if color_type == 2:
        channels = 3
    elif color_type == 6:
        channels = 4
    else:
        raise ValueError(f"unsupported PNG color type {color_type}: {path}")
    stride = width * channels
    rows: list[np.ndarray] = []
    cursor = 0
    prev = np.zeros(stride, dtype=np.uint8)
    for _ in range(height):
        ftype = raw[cursor]
        scan = np.frombuffer(raw[cursor + 1 : cursor + 1 + stride], dtype=np.uint8).copy()
        cursor += 1 + stride
        recon = _paeth_recon(ftype, scan, prev, channels)
        rows.append(recon)
        prev = recon
    rgb = np.stack(rows, axis=0).reshape(height, width, channels)
    return np.ascontiguousarray(rgb[:, :, :3])


def _paeth_recon(ftype: int, scan: np.ndarray, prev: np.ndarray, channels: int) -> np.ndarray:
    out = scan.copy()
    if ftype == 0:
        return out
    if ftype == 1:
        for i in range(channels, out.size):
            out[i] = (int(out[i]) + int(out[i - channels])) & 255
        return out
    if ftype == 2:
        return ((out.astype(np.uint16) + prev.astype(np.uint16)) & 255).astype(np.uint8)
    if ftype == 3:
        for i in range(out.size):
            left = int(out[i - channels]) if i >= channels else 0
            out[i] = (int(out[i]) + ((left + int(prev[i])) // 2)) & 255
        return out
    if ftype == 4:
        for i in range(out.size):
            a = int(out[i - channels]) if i >= channels else 0
            b = int(prev[i])
            c = int(prev[i - channels]) if i >= channels else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            out[i] = (int(out[i]) + pred) & 255
        return out
    raise ValueError(f"unsupported PNG filter {ftype}")


def draw_rect(image: np.ndarray, box: tuple[int, int, int, int], color: tuple[int, int, int], width: int = 3) -> None:
    x0, y0, x1, y1 = box
    h, w = image.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return
    t = max(1, width)
    image[y0 : min(h, y0 + t), x0:x1] = color
    image[max(0, y1 - t) : y1, x0:x1] = color
    image[y0:y1, x0 : min(w, x0 + t)] = color
    image[y0:y1, max(0, x1 - t) : x1] = color


def overlay_hud(image: np.ndarray, layout: HudLayout) -> np.ndarray:
    out = np.ascontiguousarray(image.copy())
    height, width = out.shape[:2]
    named = {
        "self_bars": layout.self_bars,
        "self_cp": layout.self_cp,
        "self_hp": layout.self_hp,
        "self_mp": layout.self_mp,
        "target_frame": layout.target_frame,
        "target_hp": layout.target_hp,
        "hotbar_f1": layout.hotbar_f1,
        "hotbar_f2": layout.hotbar_f2,
        "hotbar_f3": layout.hotbar_f3,
    }
    for name, rect in named.items():
        if rect is None or rect.empty:
            continue
        draw_rect(out, rect.pixel_box(width, height), ROI_COLORS[name])
    return out


def grab_window_frame(window_id: int, *, fps: int = 10) -> np.ndarray:
    helper = resolve_helper(build=True)
    source = SCKFrameSource(
        SCKConfig(
            helper_path=helper,
            window_id=window_id,
            fps=fps,
            max_frames=2,
            profile_path=None,
            latest_timeout_s=6.0,
        )
    )
    source.initialize()
    try:
        frame = source.latest()
        if frame.image is None:
            raise RuntimeError("empty frame")
        return np.ascontiguousarray(frame.image)
    finally:
        source.close()


def resolve_parallels_window(windows: list[dict[str, Any]]) -> dict[str, Any] | None:
    visible = [row for row in windows if row.get("on_screen")]
    for row in visible:
        if row.get("title") == "Windows 11" and "parallel" in (row.get("bundle") or "").lower():
            if float(row.get("height") or 0) >= 200:
                return row
    return None


def _safe_tag(tag: str | None) -> str:
    raw = (tag or "").strip()
    if not raw:
        return ""
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw)
    return cleaned.strip("-_")[:48]


def _parse_payload(parsed: HUDParseResult) -> dict[str, Any]:
    return {
        "valid": parsed.valid,
        "confidence": parsed.confidence,
        "self_hp_ratio": parsed.self_hp_ratio,
        "self_mp_ratio": parsed.self_mp_ratio,
        "self_cp_ratio": parsed.self_cp_ratio,
        "target_locked": parsed.target_locked,
        "target_hp_ratio": parsed.target_hp_ratio,
        "target_dead": parsed.target_dead,
        "slot_f1_ready": parsed.slot_f1_ready,
        "slot_f2_ready": parsed.slot_f2_ready,
        "slot_f3_ready": parsed.slot_f3_ready,
        "reason": parsed.reason,
    }


def _roi_boxes(layout: HudLayout, width: int, height: int) -> dict[str, Any]:
    boxes: dict[str, Any] = {}
    for name, rect in (
        ("self_bars", layout.self_bars),
        ("self_cp", layout.self_cp),
        ("self_hp", layout.self_hp),
        ("self_mp", layout.self_mp),
        ("target_frame", layout.target_frame),
        ("target_hp", layout.target_hp),
        ("hotbar_f1", layout.hotbar_f1),
        ("hotbar_f2", layout.hotbar_f2),
        ("hotbar_f3", layout.hotbar_f3),
    ):
        if rect is None or rect.empty:
            continue
        boxes[name] = {
            "norm_rect": [rect.x, rect.y, rect.w, rect.h],
            "pixel_box": list(rect.pixel_box(width, height)),
        }
    return boxes


def run_calibrate_hud(
    *,
    window_id: int | None,
    profile_path: Path,
    out_dir: Path,
    tag: str | None = None,
    image_path: Path | None = None,
) -> dict[str, Any]:
    layout = HudLayout.load(profile_path)
    suffix = _safe_tag(tag)
    if image_path is not None:
        image = read_png(image_path)
        wid = None
        title = image_path.name
        source = str(image_path)
        raw_path = image_path
        over_name = f"hud-overlay-{suffix or 'measured'}.png"
    else:
        helper = resolve_helper(build=True)
        catalog = list_windows(helper)
        resolved = None
        if window_id is not None:
            for row in catalog.get("windows") or []:
                if int(row.get("id") or 0) == window_id:
                    resolved = row
                    break
        if resolved is None:
            resolved = resolve_parallels_window(list(catalog.get("windows") or []))
        if resolved is None or not resolved.get("on_screen"):
            off = None
            for row in catalog.get("windows") or []:
                if row.get("title") == "Windows 11" and float(row.get("height") or 0) >= 200:
                    off = row
                    break
            return {
                "ok": False,
                "reason": "window_not_on_screen",
                "hid_sent": False,
                "window_id": int((resolved or off or {}).get("id") or 0) or None,
                "window_title": (resolved or off or {}).get("title"),
                "on_screen": bool((resolved or {}).get("on_screen")),
            }
        wid = int(resolved["id"])
        title = resolved.get("title")
        image = grab_window_frame(wid)
        source = "sck"
        raw_name = "interlude-target-active.png" if suffix == "interlude_active" else (
            f"client-reference-{suffix}.png" if suffix else "client-reference.png"
        )
        over_name = "hud-overlay-interlude.png" if suffix == "interlude_active" else (
            f"hud-overlay-{suffix}.png" if suffix else "hud-overlay.png"
        )
        raw_path = out_dir / raw_name
        write_png(raw_path, image)
    overlay = overlay_hud(image, layout)
    out_dir.mkdir(parents=True, exist_ok=True)
    over_path = out_dir / over_name
    write_png(over_path, overlay)
    height, width = image.shape[:2]
    parsed = HUDParser(layout).parse(image)
    return {
        "ok": True,
        "hid_sent": False,
        "window_id": wid,
        "window_title": title,
        "width": width,
        "height": height,
        "mean_luma": float(image.mean()),
        "profile": str(profile_path),
        "reference": str(raw_path),
        "overlay": str(over_path),
        "source": source,
        "roi": _roi_boxes(layout, width, height),
        "roi_source": "profile",
        "tag": suffix or None,
        "parse": _parse_payload(parsed),
    }
