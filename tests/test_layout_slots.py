from pathlib import Path

import numpy as np

from l2_brain.cli import main
from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster
from l2_brain.live.layout_slots_probe import run_layout_slots_probe
from l2_brain.live.s4_probe import ScriptedGrabber
from l2_brain.tools.layout_calibrator import draw_layout_overlay, run_layout_grid
from l2_brain.tools.layout_overlay import run_layout_overlay, slot_guides
from l2_brain.vision.layout_slots import LayoutSlots
from l2_brain.vision.ui_manager import WindowManager


class _Clock:
    def __init__(self) -> None:
        self.t = 10**12

    def __call__(self) -> int:
        return self.t

    def advance_ms(self, ms: int) -> None:
        self.t += ms * 1_000_000


def _profile(path: Path) -> Path:
    path.write_text(
        """
{
  "layout_slots": {
    "ref_window": [2056, 1290],
    "hotkey_close": "escape",
    "slots": {
      "slot_dialog_left": {"window_px": [60, 140, 400, 520], "title_bar": [0, 0, 400, 30]},
      "slot_modal_right": {"window_px": [1636, 140, 360, 480], "title_bar": [0, 0, 360, 30]},
      "hud_self": {"window_px": [10, 10, 220, 70], "title_bar": [0, 0, 220, 24]}
    }
  }
}
""".strip(),
        encoding="utf-8",
    )
    return path


def test_slot_b_is_park_target() -> None:
    slots = LayoutSlots.load(Path("config/window_profiles/parallels_l2.json"))
    x, y, w, h = slots.get("slot_modal_right").window_px
    assert x == slots.ref_window[0] - 420
    assert (y, w, h) == (140, 360, 480)
    assert slots.get("slot_dialog_left").window_px == (60, 140, 400, 520)


def test_overlay_guides_scale_to_host_window() -> None:
    slots = LayoutSlots.load(Path("config/window_profiles/parallels_l2.json"))
    assert slots.ref_window == (2560, 1600)
    assert slots.get("slot_modal_right").window_px == (2140, 140, 360, 480)
    host = {row["id"]: row for row in slot_guides(slots, 2056, 1290)}
    assert host["slot_modal_right"]["x"] == round(2140 * 2056 / 2560)
    assert host["slot_dialog_left"]["x"] == round(60 * 2056 / 2560)


def test_overlay_guides_and_no_show(tmp_path: Path) -> None:
    profile = _profile(tmp_path / "p.json")
    slots = LayoutSlots.load(profile)
    guides = {row["id"]: row for row in slot_guides(slots)}
    assert guides["slot_dialog_left"]["x"] == 60
    assert guides["slot_modal_right"]["x"] == 1636
    payload = run_layout_overlay(profile_path=profile, seconds=0, show=False)
    assert payload["hid_sent"] is False
    assert payload["shown"] is False or payload.get("reason") == "window_not_on_screen"
    assert payload["click_through"] is True
    assert main(["layout-overlay", "--no-show", "--seconds", "0", "--profile", str(profile)]) in {0, 2}


def test_is_slot_occupied_title_bar_only() -> None:
    slots = LayoutSlots.load(Path("config/window_profiles/parallels_l2.json"))
    manager = WindowManager(slots)
    empty = np.full((1290, 2056, 3), 90, dtype=np.uint8)
    empty[:, :, 1] = 110
    assert manager.is_slot_occupied("slot_modal_right", empty) is False
    grass = np.full((1290, 2056, 3), 40, dtype=np.uint8)
    assert manager.is_slot_occupied("slot_dialog_left", grass) is False
    assert manager.is_slot_occupied("slot_modal_right", grass) is False
    busy = empty.copy()
    x0, y0, x1, y1 = slots.title_box_on_frame("slot_modal_right", 2056, 1290)
    busy[y0:y1, x0:x1] = (22, 20, 18)
    busy[y0 : y0 + 3, x0:x1] = (210, 198, 160)
    assert manager.is_slot_occupied("slot_modal_right", busy) is True
    assert manager.is_slot_occupied("slot_dialog_left", busy) is False


def test_window_stack_and_reset() -> None:
    slots = LayoutSlots.from_mapping(
        {"layout_slots": {"ref_window": [100, 100], "slots": {"slot_modal_right": {"window_px": [10, 10, 20, 20]}}}}
    )
    manager = WindowManager(slots)
    manager.open_modal("inventory")
    manager.open_modal("macros")
    assert manager.open_windows == ["inventory", "macros"]
    assert manager.close_active_modal() == "macros"
    assert manager.reset_all() == ["inventory"]
    assert manager.open_windows == []


def test_overlay_and_cli_from_png(tmp_path: Path) -> None:
    profile = _profile(tmp_path / "p.json")
    frame = np.full((258, 411, 3), 40, dtype=np.uint8)
    slots = LayoutSlots.load(profile)
    over = draw_layout_overlay(frame, slots)
    assert over.shape == frame.shape
    assert int(over[30, 20, 1]) >= 40
    src = tmp_path / "src.png"
    from l2_brain.vision.calibrate_hud import write_png

    write_png(src, frame)
    out = tmp_path / "guide.png"
    payload = run_layout_grid(save_path=out, profile_path=profile, image_path=src)
    assert payload["ok"] is True
    assert payload["hid_sent"] is False
    assert Path(payload["png"]).is_file()
    assert payload["slot_a"][2] - payload["slot_a"][0] > 10
    code = main(["layout-grid", "--from-png", str(src), "--profile", str(profile), "--save", str(tmp_path / "cli.png")])
    assert code == 0
    assert (tmp_path / "cli.png").is_file()


def test_layout_slots_flags_required(tmp_path: Path) -> None:
    payload = run_layout_slots_probe(live=True, danger_confirmed=False, out_path=tmp_path / "x.json")
    assert payload["aborted"] == "live_flags_required"
    assert payload["hid_sent"] is False
    assert payload["farm"] is False
    assert main(["layout-slots", "--out", str(tmp_path / "cli.json")]) == 2


def test_probe_tab_occupies_and_escape_frees(tmp_path: Path) -> None:
    clock = _Clock()
    backend = CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=RecordingPoster(),
        focus_probe=lambda: True,
        now_ns=clock,
    )
    profile = _profile(tmp_path / "p.json")
    slots = LayoutSlots.load(profile)
    empty = np.full((1290, 2056, 3), 100, dtype=np.uint8)
    busy = empty.copy()
    x0, y0, x1, y1 = slots.title_box_on_frame("slot_modal_right", 2056, 1290)
    busy[y0:y1, x0:x1] = (18, 16, 14)
    busy[y0 : y0 + 3, x0:x1] = (210, 198, 160)

    class _Seq(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            tabs = sum(1 for row in backend.log if row.key == "tab" and row.hold_duration_ms == 40)
            esc = sum(1 for row in backend.log if row.key == "escape" and row.hold_duration_ms == 40)
            if tabs >= 1 and esc < 2:
                return busy
            return empty

    payload = run_layout_slots_probe(
        live=True,
        danger_confirmed=True,
        grabber=_Seq([empty]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=profile,
        out_path=tmp_path / "layout.json",
    )
    assert payload["ok"] is True
    assert payload["clean_free"] is True
    assert payload["after_tab_occupied"] is True
    assert payload["after_escape_free"] is True
    assert payload["farm"] is False
    assert payload["tab_sent"] is True
    assert not any(row.key == "F2" for row in backend.log)
