from pathlib import Path

import numpy as np

from l2_brain.cli import main
from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster
from l2_brain.live.npc_dialog_probe import run_npc_dialog_probe
from l2_brain.live.s4_probe import ScriptedGrabber
from l2_brain.vision.dialog_parser import extract_menu_items, is_dialog_open, parse_dialog
from l2_brain.vision.hud_parser import HUDParser, HudLayout


class _Clock:
    def __init__(self) -> None:
        self.t = 10**12

    def __call__(self) -> int:
        return self.t

    def advance_ms(self, ms: int) -> None:
        self.t += ms * 1_000_000


def _write_profile(path: Path) -> Path:
    import json

    mapping = {
        "hud": {
            "self_bars": {"norm_rect": [0.0, 0.0, 0.4, 0.18]},
            "self_cp": {"norm_rect": [0.0, 0.0, 0.4, 0.06]},
            "self_hp": {"norm_rect": [0.0, 0.06, 0.4, 0.06]},
            "self_mp": {"norm_rect": [0.0, 0.12, 0.4, 0.06]},
            "target_frame": {"norm_rect": [0.5, 0.0, 0.5, 0.18]},
            "target_hp": {"norm_rect": [0.5, 0.06, 0.5, 0.06]},
        }
    }
    HUDParser(HudLayout.from_mapping(mapping))
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


def _scene(*, locked: bool, dialog: bool = False) -> np.ndarray:
    image = np.full((200, 300, 3), 22, dtype=np.uint8)
    image[0:12, 0:80] = (220, 180, 20)
    image[12:24, 0:70] = (220, 20, 20)
    image[24:36, 0:60] = (20, 40, 220)
    if locked:
        image[0:36, 150:300] = (40, 32, 28)
        image[12:24, 150:230] = (220, 20, 20)
    if dialog:
        image[40:150, 75:225] = (210, 188, 140)
        image[70:76, 90:180] = (40, 70, 220)
    return image


def _html_scene(*, locked: bool) -> np.ndarray:
    image = _scene(locked=locked, dialog=False)
    image[40:170, 18:120] = (28, 26, 24)
    for y in (55, 75, 95, 115):
        image[y : y + 10, 26:110] = (60, 90, 210)
    return image


def test_dialog_closed_on_grass() -> None:
    frame = np.full((200, 300, 3), 28, dtype=np.uint8)
    frame[:, :, 1] = 48
    parsed = parse_dialog(frame)
    assert is_dialog_open(frame) is False
    assert parsed.open is False
    assert extract_menu_items(frame) == []


def test_gold_nameplates_are_not_dialog() -> None:
    image = np.full((200, 300, 3), 70, dtype=np.uint8)
    image[:, :, 0] = 82
    image[:, :, 1] = 64
    image[:, :, 2] = 48
    image[60:66, 140:190] = (220, 180, 40)
    image[100:106, 120:170] = (220, 180, 40)
    parsed = parse_dialog(image)
    assert parsed.open is False
    assert parsed.reason == "no_dialog"
    assert extract_menu_items(image) == []


def test_dialog_html_links_on_dark_panel() -> None:
    image = _html_scene(locked=False)
    items = extract_menu_items(image)
    parsed = parse_dialog(image)
    assert is_dialog_open(image) is True
    assert parsed.open is True
    assert parsed.reason == "html_links"
    assert len(items) >= 3
    assert items == sorted(items, key=lambda row: row[1])
    assert all(x / image.shape[1] <= 0.42 for x, _y in items)


def test_center_target_marker_is_not_html_dialog() -> None:
    image = np.full((200, 300, 3), 40, dtype=np.uint8)
    image[88:130, 140:175] = (40, 80, 220)
    image[100:140, 148:168] = (50, 90, 230)
    assert extract_menu_items(image) == []
    assert is_dialog_open(image) is False
    assert parse_dialog(image).open is False


def test_dialog_parchment_and_blue_link() -> None:
    frame = _scene(locked=True, dialog=True)
    parsed = parse_dialog(frame)
    assert parsed.open is True
    assert parsed.confidence >= 0.35
    assert parsed.first_link is not None
    assert parsed.link_kind in {"blue", "fallback_center"}
    assert 75 <= parsed.first_link[0] <= 225


def test_flags_required(tmp_path: Path) -> None:
    payload = run_npc_dialog_probe(live=True, danger_confirmed=False, out_path=tmp_path / "x.json")
    assert payload["aborted"] == "live_flags_required"
    assert payload["hid_sent"] is False
    assert payload["farm"] is False


def test_cli_without_flags(tmp_path: Path) -> None:
    out = tmp_path / "cli.json"
    code = main(["s4-npc-dialog", "--slot", "F5", "--out", str(out)])
    assert code == 2
    assert "live_flags_required" in out.read_text(encoding="utf-8")


def test_probe_lock_dialog_click(tmp_path: Path) -> None:
    clock = _Clock()
    backend = CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=RecordingPoster(),
        focus_probe=lambda: True,
        now_ns=clock,
    )
    idle = _scene(locked=False)
    locked = _scene(locked=True)
    dialog = _scene(locked=True, dialog=True)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            clicks = sum(1 for row in backend.log if row.action_type == "GroundClick")
            f5 = sum(1 for row in backend.log if row.key == "F5")
            if clicks >= 1:
                return dialog
            if f5 >= 1:
                return locked
            return idle

    payload = run_npc_dialog_probe(
        live=True,
        danger_confirmed=True,
        slot="F5",
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "npc.json",
        png_path=tmp_path / "npc_dialog_detected.png",
        last_png_path=tmp_path / "npc_dialog_last.png",
        locked_png_path=tmp_path / "npc_dialog_locked.png",
    )
    assert payload["ok"] is True
    assert payload["target_acquired"] is True
    assert payload["dialog_detected"] is True
    assert payload["talk_click_dispatched"] is True
    assert payload["click_dispatched"] is True
    assert payload["escape_sent"] is True
    assert payload["farm"] is False
    assert payload["approach_time_sec"] is not None
    assert "p95" in payload["parse_dialog"]
    assert (tmp_path / "npc_dialog_detected.png").is_file()
    assert sum(1 for row in backend.log if row.key == "F5") == 1
    assert not any(row.key in ("F1", "F2", "F3") for row in backend.log)
    assert sum(1 for row in backend.log if row.action_type == "GroundClick") >= 2
    assert any(row.key == "escape" for row in backend.log)
    assert payload["quest_link_clicks"] >= 1
    assert payload["talk_clicks"] == 1
    assert (tmp_path / "npc_dialog_locked.png").is_file()


def _run_probe(tmp_path: Path, grabber: ScriptedGrabber, backend: CGEventInputBackend, clock: _Clock):
    return run_npc_dialog_probe(
        live=True,
        danger_confirmed=True,
        slot="F5",
        grabber=grabber,
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "npc.json",
        png_path=tmp_path / "npc_dialog_detected.png",
        last_png_path=tmp_path / "npc_dialog_last.png",
        locked_png_path=tmp_path / "npc_dialog_locked.png",
    )


def test_probe_restarts_capture_on_sense_loss(tmp_path: Path) -> None:
    clock = _Clock()
    backend = CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=RecordingPoster(),
        focus_probe=lambda: True,
        now_ns=clock,
    )
    idle = _scene(locked=False)
    locked = _scene(locked=True)
    dialog = _scene(locked=True, dialog=True)

    class _Flaky(ScriptedGrabber):
        starts = 0
        failed = False

        def start(self) -> None:
            self.starts += 1

        def latest_image(self) -> np.ndarray:
            clicks = sum(1 for row in backend.log if row.action_type == "GroundClick")
            f5 = sum(1 for row in backend.log if row.key == "F5")
            if clicks >= 1 and self.starts <= 1:
                raise RuntimeError("source lost")
            if clicks >= 1:
                return dialog
            if f5 >= 1:
                return locked
            return idle

    grabber = _Flaky([idle])
    payload = _run_probe(tmp_path, grabber, backend, clock)
    assert payload["ok"] is True
    assert grabber.starts >= 2
    assert payload["capture_restarts"] >= 1
    assert payload["dialog_detected"] is True


def test_probe_skips_talk_click_if_dialog_already_open(tmp_path: Path) -> None:
    clock = _Clock()
    backend = CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=RecordingPoster(),
        focus_probe=lambda: True,
        now_ns=clock,
    )
    idle = _scene(locked=False)
    ready = _scene(locked=True, dialog=True)

    class _Ready(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            f5 = sum(1 for row in backend.log if row.key == "F5")
            return ready if f5 >= 1 else idle

    payload = _run_probe(tmp_path, _Ready([idle]), backend, clock)
    assert payload["ok"] is True
    assert payload["dialog_detected"] is True
    assert payload["talk_clicks"] == 0
    assert payload["quest_link_clicks"] >= 1
    assert not any(row.get("step") == "approach" for row in payload["steps"])
    assert sum(1 for row in payload["steps"] if row.get("already_open")) == 1


def test_live_locked_png_is_html_dialog() -> None:
    from l2_brain.vision.calibrate_hud import read_png

    path = Path("tests/fixtures/newbie_guide_dialog.png")
    image = read_png(path)
    items = extract_menu_items(image)
    parsed = parse_dialog(image)
    assert is_dialog_open(image) is True
    assert parsed.open is True
    assert parsed.reason == "html_links"
    assert parsed.link_kind == "blue"
    assert len(items) >= 3
    assert all(x / image.shape[1] <= 0.42 for x, _y in items)
