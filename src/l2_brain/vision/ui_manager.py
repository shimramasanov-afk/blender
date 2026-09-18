"""UI window stack. Slots only. Escape closes. No farm. No OCR."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from l2_brain.io.actions import HoldKey
from l2_brain.io.cgevent_backend import CGEventInputBackend
from l2_brain.vision.layout_slots import LayoutSlots

TITLE_LUMA_MAX = 58.0
TITLE_STD_MAX = 36.0
TITLE_STD_MIN = 12.0
RIM_LUMA_MIN = 80.0
BODY_STD_MIN = 20.0
RESET_PAUSE_S = 0.15


class WindowManager:
    def __init__(self, slots: LayoutSlots) -> None:
        self.slots = slots
        self.open_windows: list[str] = []

    def open_modal(self, name: str) -> None:
        token = str(name)
        if token in self.open_windows:
            self.open_windows.remove(token)
        self.open_windows.append(token)

    def close_active_modal(self) -> str | None:
        if not self.open_windows:
            return None
        return self.open_windows.pop()

    def reset_all(self) -> list[str]:
        was = list(self.open_windows)
        self.open_windows.clear()
        return was

    def is_slot_occupied(self, slot_name: str, frame: np.ndarray) -> bool:
        rgb = np.asarray(frame)
        if rgb.ndim != 3 or rgb.shape[2] < 3:
            return False
        height, width = rgb.shape[:2]
        x0, y0, x1, y1 = self.slots.box_on_frame(slot_name, width, height)
        tx0, ty0, tx1, ty1 = self.slots.title_box_on_frame(slot_name, width, height)
        if x1 - x0 < 8 or y1 - y0 < 8 or tx1 - tx0 < 4 or ty1 - ty0 < 3:
            return False
        title = rgb[ty0:ty1, tx0:tx1, :3]
        body = rgb[y0:y1, x0:x1, :3]
        title_luma = 0.299 * title[:, :, 0] + 0.587 * title[:, :, 1] + 0.114 * title[:, :, 2]
        body_luma = 0.299 * body[:, :, 0] + 0.587 * body[:, :, 1] + 0.114 * body[:, :, 2]
        rim_h = max(2, min(4, title_luma.shape[0] // 4))
        rim = title_luma[:rim_h]
        inner = title_luma[rim_h:] if title_luma.shape[0] > rim_h + 2 else title_luma
        if float(rim.mean()) >= RIM_LUMA_MIN and float(inner.mean()) <= TITLE_LUMA_MAX + 4.0:
            return True
        if float(body_luma.std()) >= BODY_STD_MIN:
            return True
        inner_mean = float(inner.mean())
        inner_std = float(inner.std())
        return inner_mean <= TITLE_LUMA_MAX and TITLE_STD_MIN <= inner_std <= TITLE_STD_MAX

    def occupied_slots(self, frame: np.ndarray) -> list[str]:
        found: list[str] = []
        for name in ("slot_dialog_left", "slot_modal_right"):
            if name in self.slots.slots and self.is_slot_occupied(name, frame):
                found.append(name)
        return found

    def reset_ui(
        self,
        backend: CGEventInputBackend,
        frame_probe: Callable[[], np.ndarray | None],
        *,
        sleeper: Callable[[float], None],
        payload: dict[str, Any] | None = None,
        max_escapes: int = 2,
    ) -> bool:
        log = payload if payload is not None else {}
        for _ in range(max(1, max_escapes)):
            frame = frame_probe()
            if frame is None:
                log["aborted"] = log.get("aborted") or "no_frame"
                return False
            if not self.occupied_slots(frame):
                self.reset_all()
                return True
            ev = backend.send_action(HoldKey(key="escape", duration_ms=40, state="down"))
            log["hid_sent"] = bool(log.get("hid_sent") or ev.hid_sent)
            if not ev.accepted:
                log["aborted"] = ev.reason
                return False
            backend.send_action(HoldKey(key="escape", duration_ms=0, state="up"))
            sleeper(RESET_PAUSE_S)
        frame = frame_probe()
        if frame is None:
            return False
        clear = not self.occupied_slots(frame)
        if clear:
            self.reset_all()
        return clear
