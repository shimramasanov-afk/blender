"""Aggregate existing parsers into WorldState. No HID. No input backend import."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Protocol

import numpy as np

from l2_brain.experiment.clocks import mono_ns
from l2_brain.live.world_state import WorldState, empty_world_state
from l2_brain.vision.dialog_parser import extract_menu_items, is_dialog_open, parse_dialog
from l2_brain.vision.hud_parser import HUDParser


class FrameProvider(Protocol):
    def latest_image(self) -> np.ndarray: ...


class PerceptionHub:
    def __init__(
        self,
        hud: HUDParser,
        *,
        focus_probe: Callable[[], bool],
        frames: FrameProvider | None = None,
        now_ns: Callable[[], int] | None = None,
        motion_fn: Callable[[np.ndarray], float | None] | None = None,
        modal_fn: Callable[[np.ndarray], bool | None] | None = None,
    ) -> None:
        self.hud = hud
        self._focus_probe = focus_probe
        self.frames = frames
        self._now = now_ns or mono_ns
        self._motion_fn = motion_fn
        self._modal_fn = modal_fn
        self.last_state: WorldState | None = None
        self.last_image: np.ndarray | None = None
        self.last_hud: Any | None = None
        self.last_dialog: Any | None = None
        self.last_parse_dialog_ms: float | None = None
        self.last_hud_parse_ms: float | None = None

    def observe(self) -> WorldState:
        focus_ok = bool(self._focus_probe())
        if self.frames is None:
            self.last_image = None
            self.last_hud = None
            self.last_dialog = None
            state = empty_world_state(timestamp_ns=self._now(), last_error="no_frame_source")
            self.last_state = replace(state, focus_ok=focus_ok, capture_ok=False, last_error="no_frame_source")
            return self.last_state
        try:
            image = self.frames.latest_image()
        except Exception:  # noqa: BLE001 — capture failure is a WorldState fact
            self.last_image = None
            self.last_hud = None
            self.last_dialog = None
            state = empty_world_state(timestamp_ns=self._now(), last_error="capture_lost")
            self.last_state = replace(state, focus_ok=focus_ok, capture_ok=False, last_error="capture_lost")
            return self.last_state
        return self.update(image, capture_ok=True, focus_ok=focus_ok)

    def update(
        self,
        frame: np.ndarray | None,
        *,
        capture_ok: bool,
        focus_ok: bool,
        last_error: str | None = None,
    ) -> WorldState:
        now = self._now()
        if frame is None or not capture_ok:
            self.last_image = None
            self.last_hud = None
            self.last_dialog = None
            state = empty_world_state(timestamp_ns=now, last_error=last_error or "no_frame")
            self.last_state = replace(state, focus_ok=focus_ok, capture_ok=False)
            return self.last_state
        t_hud = time.perf_counter()
        parsed = self.hud.parse(frame)
        self.last_hud_parse_ms = (time.perf_counter() - t_hud) * 1000.0
        items = tuple(extract_menu_items(frame)) if parsed.valid or frame.size else ()
        t_dialog = time.perf_counter()
        dialog = parse_dialog(frame) if frame.size else None
        self.last_parse_dialog_ms = (time.perf_counter() - t_dialog) * 1000.0
        self.last_image = frame
        self.last_hud = parsed
        self.last_dialog = dialog
        if parsed.valid:
            dialog_open = bool(is_dialog_open(frame) or (dialog is not None and dialog.open))
        else:
            dialog_open = bool(is_dialog_open(frame)) if frame.size else None
        motion = None
        if self._motion_fn is not None:
            motion = self._motion_fn(frame)
        modal = None
        if self._modal_fn is not None:
            modal = self._modal_fn(frame)
        height, width = int(frame.shape[0]), int(frame.shape[1])
        self.last_state = WorldState(
            timestamp_ns=now,
            capture_ok=True,
            focus_ok=focus_ok,
            self_hp=parsed.self_hp_ratio if parsed.valid else None,
            self_cp=parsed.self_cp_ratio if parsed.valid else None,
            self_mp=parsed.self_mp_ratio if parsed.valid else None,
            target_locked=parsed.target_locked if parsed.valid else None,
            target_hp=parsed.target_hp_ratio if parsed.valid else None,
            target_dead=parsed.target_dead if parsed.valid else None,
            dialog_open=dialog_open,
            dialog_items=items,
            ui_modal_open=modal,
            motion_magnitude=motion,
            last_error=None if parsed.valid else parsed.reason,
            frame_width=width,
            frame_height=height,
            hud_valid=parsed.valid,
        )
        return self.last_state
