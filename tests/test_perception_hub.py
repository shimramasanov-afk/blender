import ast
from pathlib import Path

import numpy as np

from l2_brain.live.perception import PerceptionHub
from l2_brain.live.s4_probe import ScriptedGrabber
from l2_brain.live.world_state import WorldState
from l2_brain.vision.hud_parser import HUDParser, HudLayout

from test_hud_parser import _layout as _hud_layout
from test_hud_parser import _scene as _hud_scene
from test_npc_dialog import _html_scene, _scene


def test_perception_source_has_no_cgevent() -> None:
    text = Path("src/l2_brain/live/perception.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert not any("cgevent" in name for name in imports)
    assert "CGEvent" not in text


def test_hp_lock_death_and_missing_stay_none() -> None:
    hub = PerceptionHub(
        HUDParser(_hud_layout()),
        focus_probe=lambda: True,
        frames=ScriptedGrabber(frames=[_hud_scene(hp=0.5, mp=1.0, cp=0.25, target=True, target_hp=0.4)]),
    )
    state = hub.observe()
    assert state.capture_ok is True
    assert abs((state.self_hp or -1) - 0.5) <= 0.05
    assert state.target_locked is True
    assert abs((state.target_hp or -1) - 0.4) <= 0.05
    assert state.target_dead is False

    dead = PerceptionHub(
        HUDParser(_hud_layout()),
        focus_probe=lambda: True,
        frames=ScriptedGrabber(frames=[_hud_scene(hp=0.5, mp=1.0, cp=0.25, target=True, target_hp=0.0)]),
    ).observe()
    assert dead.target_dead is True

    lost = PerceptionHub(
        HUDParser(_hud_layout()),
        focus_probe=lambda: True,
        frames=ScriptedGrabber(frames=[]),
    )
    failed = lost.observe()
    assert failed.capture_ok is False
    assert failed.self_hp is None
    assert failed.target_locked is None
    assert failed.target_hp is None
    assert failed.last_error == "capture_lost"


def test_dialog_detected_and_absent() -> None:
    hub = PerceptionHub(
        HUDParser(HudLayout.from_mapping({"hud": {
            "self_bars": {"norm_rect": [0.0, 0.0, 0.4, 0.18]},
            "self_hp": {"norm_rect": [0.0, 0.06, 0.4, 0.06]},
            "self_mp": {"norm_rect": [0.0, 0.12, 0.4, 0.06]},
            "self_cp": {"norm_rect": [0.0, 0.0, 0.4, 0.06]},
            "target_frame": {"norm_rect": [0.5, 0.0, 0.5, 0.18]},
            "target_hp": {"norm_rect": [0.5, 0.06, 0.5, 0.06]},
        }})),
        focus_probe=lambda: True,
        frames=ScriptedGrabber(frames=[_html_scene(locked=True)]),
    )
    open_state = hub.observe()
    assert open_state.dialog_open is True
    assert len(open_state.dialog_items) >= 2

    closed = PerceptionHub(
        HUDParser(hub.hud.layout),
        focus_probe=lambda: True,
        frames=ScriptedGrabber(frames=[_scene(locked=False)]),
    ).observe()
    assert closed.dialog_open is False


def test_focus_failure_and_no_quest_fields() -> None:
    hub = PerceptionHub(
        HUDParser(_hud_layout()),
        focus_probe=lambda: False,
        frames=ScriptedGrabber(frames=[_hud_scene(hp=1.0, mp=1.0, cp=1.0, target=False)]),
    )
    state = hub.observe()
    assert state.focus_ok is False
    assert "quest" not in WorldState.__dataclass_fields__
    assert not hasattr(state, "quest_state")
    assert not hasattr(state, "objective")


def test_perception_does_not_send_input() -> None:
    from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster

    poster = RecordingPoster()
    CGEventInputBackend(
        1,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=poster,
        focus_probe=lambda: True,
    )
    PerceptionHub(
        HUDParser(_hud_layout()),
        focus_probe=lambda: True,
        frames=ScriptedGrabber(frames=[np.full((40, 40, 3), 18, dtype=np.uint8)]),
    ).observe()
    assert poster.calls == []
