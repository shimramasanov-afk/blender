from pathlib import Path

import numpy as np

from l2_brain.telemetry.events import EntityDefeated, TargetState
from l2_brain.telemetry.hub import TelemetryHub
from l2_brain.telemetry.vision_bridge import VisionTelemetryBridge
from l2_brain.vision.calibrate_hud import read_png
from l2_brain.vision.hud_parser import HP_RED, HUDParser, HudLayout, _in_range, detect_target_plate

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "config" / "window_profiles" / "parallels_l2.json"
LIVE = ROOT / "docs" / "evidence" / "live-s4"
ACTIVE = LIVE / "interlude-target-active.png"
REFERENCE = LIVE / "client-reference.png"


def _layout() -> HudLayout:
    return HudLayout.from_mapping(
        {
            "hud": {
                "self_bars": {"norm_rect": [0.0, 0.0, 0.5, 0.3]},
                "self_cp": {"norm_rect": [0.0, 0.0, 0.5, 0.1]},
                "self_hp": {"norm_rect": [0.0, 0.1, 0.5, 0.1]},
                "self_mp": {"norm_rect": [0.0, 0.2, 0.5, 0.1]},
                "target_frame": {"norm_rect": [0.5, 0.0, 0.5, 0.3]},
                "target_hp": {"norm_rect": [0.5, 0.1, 0.5, 0.1]},
            }
        }
    )


def _scene(*, target: bool, target_hp: float = 1.0) -> np.ndarray:
    image = np.full((100, 200, 3), 18, dtype=np.uint8)
    image[10:20, 0:100] = (220, 20, 20)
    image[20:30, 0:100] = (20, 40, 220)
    image[0:10, 0:100] = (220, 180, 20)
    if not target:
        return image
    image[0:30, 100:200] = (40, 40, 40)
    image[0, 100:200] = 220
    image[29, 100:200] = 220
    image[:, 100] = 220
    image[:, 199] = 220
    cut = int(100 * target_hp)
    if cut > 0:
        image[10:20, 100 : 100 + cut] = (220, 20, 20)
    return image


def test_gremlin_frame_locked_with_hp() -> None:
    if not ACTIVE.exists():
        return
    parsed = HUDParser.from_profile(PROFILE).parse(read_png(ACTIVE))
    assert parsed.valid
    assert parsed.target_locked is True
    assert parsed.target_dead is False
    assert abs((parsed.target_hp_ratio or -1) - 0.44) <= 0.05


def test_f44_frame_has_no_target() -> None:
    if not REFERENCE.exists():
        return
    parsed = HUDParser.from_profile(PROFILE).parse(read_png(REFERENCE))
    assert parsed.valid
    assert parsed.target_locked is False
    assert parsed.target_hp_ratio is None
    assert parsed.target_dead is False


def test_empty_plate_is_dead_not_missing() -> None:
    parsed = HUDParser(_layout()).parse(_scene(target=True, target_hp=0.0))
    assert parsed.valid
    assert parsed.target_locked is True
    assert parsed.target_hp_ratio == 0.0
    assert parsed.target_dead is True


def test_gremlin_plate_survives_cleared_bar() -> None:
    if not ACTIVE.exists():
        return
    image = read_png(ACTIVE)
    parser = HUDParser.from_profile(PROFILE)
    box = parser.layout.target_hp.pixel_box(image.shape[1], image.shape[0])
    x0, y0, x1, y1 = box
    crop = image[y0:y1, x0:x1]
    crop[_in_range(crop, *HP_RED)] = (42, 32, 26)
    parsed = parser.parse(image)
    assert parsed.target_locked is True
    assert parsed.target_hp_ratio == 0.0
    assert parsed.target_dead is True


def test_detect_target_plate_rejects_stone_contrast() -> None:
    stone = np.full((40, 80, 3), 70, dtype=np.uint8)
    stone[0, :] = 230
    stone[-1, :] = 230
    stone[:, 0] = 230
    stone[:, -1] = 230
    assert detect_target_plate(stone) is False


def test_bridge_emits_defeat_on_empty_plate() -> None:
    hub = TelemetryHub()
    bridge = VisionTelemetryBridge(hub)
    parser = HUDParser(_layout())
    assert bridge.publish(parser.parse(_scene(target=True, target_hp=0.5)), now_ns=1) == 2
    n = bridge.publish(parser.parse(_scene(target=True, target_hp=0.0)), now_ns=2)
    assert n >= 2
    dead = hub.get_latest(EntityDefeated)
    target = hub.get_latest(TargetState)
    assert dead is not None and dead.is_target is True and dead.source == "ui_vision"
    assert dead.xp_gained == 0
    assert target is not None and target.locked is True
    assert target.hp_percent == 0.0
    assert bridge.publish(parser.parse(_scene(target=True, target_hp=0.0)), now_ns=3) == 0


def test_bridge_does_not_treat_high_hp_drop_as_defeat() -> None:
    hub = TelemetryHub()
    bridge = VisionTelemetryBridge(hub)
    parser = HUDParser(_layout())
    bridge.publish(parser.parse(_scene(target=True, target_hp=0.7)), now_ns=1)
    bridge.publish(parser.parse(_scene(target=False)), now_ns=2)
    assert hub.get_latest(EntityDefeated) is None
    target = hub.get_latest(TargetState)
    assert target is not None and target.locked is False
    assert target.hp_percent is None
