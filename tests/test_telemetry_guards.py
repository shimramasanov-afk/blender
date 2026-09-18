from pathlib import Path

import numpy as np

from l2_brain.telemetry.events import EntityDefeated, TargetState
from l2_brain.telemetry.hub import TelemetryHub
from l2_brain.telemetry.vision_bridge import VisionTelemetryBridge
from l2_brain.vision.calibrate_hud import read_png
from l2_brain.vision.hud_parser import HUDParser, HudLayout, is_slot_ready

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "config" / "window_profiles" / "parallels_l2.json"
ACTIVE = ROOT / "docs" / "evidence" / "live-s4" / "interlude-target-active.png"


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


def test_drop_at_hp_044_is_target_lost_not_defeat() -> None:
    hub = TelemetryHub()
    bridge = VisionTelemetryBridge(hub)
    parser = HUDParser(_layout())
    bridge.publish(parser.parse(_scene(target=True, target_hp=0.44)), now_ns=1)
    bridge.publish(parser.parse(_scene(target=False)), now_ns=2)
    assert hub.get_latest(EntityDefeated) is None
    target = hub.get_latest(TargetState)
    assert target is not None
    assert target.locked is False
    assert target.hp_percent is None


def test_vanish_after_zero_hp_is_defeat() -> None:
    hub = TelemetryHub()
    bridge = VisionTelemetryBridge(hub)
    parser = HUDParser(_layout())
    bridge.publish(parser.parse(_scene(target=True, target_hp=0.4)), now_ns=1)
    bridge.publish(parser.parse(_scene(target=True, target_hp=0.0)), now_ns=2)
    first = hub.get_latest(EntityDefeated)
    assert first is not None
    bridge.publish(parser.parse(_scene(target=False)), now_ns=3)
    assert hub.get_latest(EntityDefeated) is first
    target = hub.get_latest(TargetState)
    assert target is not None and target.locked is False


def test_vanish_after_critical_hp_is_defeat() -> None:
    hub = TelemetryHub()
    bridge = VisionTelemetryBridge(hub)
    parser = HUDParser(_layout())
    bridge.publish(parser.parse(_scene(target=True, target_hp=0.05)), now_ns=1)
    bridge.publish(parser.parse(_scene(target=False)), now_ns=2)
    dead = hub.get_latest(EntityDefeated)
    assert dead is not None and dead.is_target is True
    target = hub.get_latest(TargetState)
    assert target is not None and target.locked is False


def test_bright_slot_ready_dark_slot_not() -> None:
    bright = np.zeros((24, 24, 3), dtype=np.uint8)
    bright[4:20, 4:20] = (40, 200, 70)
    dark = (bright.astype(np.float32) * 0.35).astype(np.uint8)
    empty = np.full((24, 24, 3), 32, dtype=np.uint8)
    assert is_slot_ready(bright) is True
    assert is_slot_ready(dark) is False
    assert is_slot_ready(empty) is False


def test_recorded_f1_f3_ready_on_gremlin_frame() -> None:
    if not ACTIVE.exists():
        return
    parsed = HUDParser.from_profile(PROFILE).parse(read_png(ACTIVE))
    assert parsed.slot_f1_ready is True
    assert parsed.slot_f2_ready is True
    assert parsed.slot_f3_ready is True
