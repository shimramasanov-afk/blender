from pathlib import Path

import numpy as np

from l2_brain.telemetry.events import HealthUpdate, TargetState
from l2_brain.telemetry.hub import TelemetryHub
from l2_brain.telemetry.vision_bridge import VisionTelemetryBridge
from l2_brain.vision.calibrate_hud import read_png
from l2_brain.vision.hud_parser import HUDParser, HudLayout, extract_bar_ratio

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "config" / "window_profiles" / "parallels_l2.json"
SHIFTED = ROOT / "tests" / "fixtures" / "hud_self_shifted.png"


def _bar(width: int, fill: float, color: tuple[int, int, int], height: int = 8) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    cut = int(round(width * fill))
    image[:, :cut] = color
    return image


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


def _scene(*, hp: float, mp: float, cp: float, target: bool, target_hp: float = 1.0) -> np.ndarray:
    image = np.full((100, 200, 3), 18, dtype=np.uint8)
    image[0:10, 0:100] = 12
    image[10:20, 0:100] = 12
    image[20:30, 0:100] = 12
    image[0:10, 0 : int(100 * cp)] = (220, 180, 20)
    image[10:20, 0 : int(100 * hp)] = (220, 20, 20)
    image[20:30, 0 : int(100 * mp)] = (20, 40, 220)
    if target:
        image[0:30, 100:200] = (40, 40, 40)
        image[0, 100:200] = 220
        image[29, 100:200] = 220
        image[:, 100] = 220
        image[:, 199] = 220
        image[10:20, 100 : 100 + int(100 * target_hp)] = (220, 20, 20)
    return image


def test_bar_ratio_clean_levels() -> None:
    red = (220, 20, 20)
    for fill in (1.0, 0.5, 0.0):
        ratio = extract_bar_ratio(_bar(100, fill, red), "hp_red")
        assert abs(ratio - fill) <= 0.02


def test_bar_ratio_tolerates_speckle() -> None:
    crop = _bar(100, 0.5, (220, 20, 20))
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 30, size=(8, 50, 3), dtype=np.uint8)
    crop[:, 50:] = noise
    assert abs(extract_bar_ratio(crop, "hp_red") - 0.5) <= 0.02


def test_parser_reads_synthetic_hud() -> None:
    parsed = HUDParser(_layout()).parse(_scene(hp=0.5, mp=1.0, cp=0.25, target=True, target_hp=0.4))
    assert parsed.valid
    assert abs((parsed.self_hp_ratio or -1) - 0.5) <= 0.02
    assert abs((parsed.self_mp_ratio or -1) - 1.0) <= 0.02
    assert abs((parsed.self_cp_ratio or -1) - 0.25) <= 0.02
    assert parsed.target_locked is True
    assert abs((parsed.target_hp_ratio or -1) - 0.4) <= 0.02


def test_parser_recovers_shifted_self_bars() -> None:
    image = np.full((2580, 4112, 3), 36, dtype=np.uint8)
    image[127:132, 18:253] = (220, 180, 20)
    image[148:152, 18:252] = (220, 20, 20)
    image[159:172, 18:253] = (20, 40, 220)
    parsed = HUDParser.from_profile(PROFILE).parse(image)
    assert parsed.valid
    assert (parsed.self_hp_ratio or 0.0) > 0.8
    assert (parsed.self_mp_ratio or 0.0) > 0.8
    assert (parsed.self_cp_ratio or 0.0) > 0.8


def test_parser_recovers_live_shifted_strip() -> None:
    strip = read_png(SHIFTED)
    image = np.full((2580, 4112, 3), 36, dtype=np.uint8)
    image[77:361, 0:280] = strip
    parsed = HUDParser.from_profile(PROFILE).parse(image)
    assert parsed.valid
    assert (parsed.self_hp_ratio or 0.0) > 0.8
    assert (parsed.self_mp_ratio or 0.0) > 0.8


def test_parser_recovers_shifted_target_plate() -> None:
    image = np.full((2580, 4112, 3), 40, dtype=np.uint8)
    image[127:132, 18:253] = (220, 180, 20)
    image[148:152, 18:252] = (220, 20, 20)
    image[159:172, 18:253] = (20, 40, 220)
    image[80:160, 1100:1800] = (50, 35, 25)
    image[118:122, 1150:1750] = (220, 20, 20)
    parsed = HUDParser.from_profile(PROFILE).parse(image)
    assert parsed.target_locked is True
    assert (parsed.target_hp_ratio or 0.0) >= 0.15
    assert parsed.target_dead is False


def test_live_window_self_bars_are_not_a_target() -> None:
    image = np.full((1290, 2056, 3), 40, dtype=np.uint8)
    image[127:132, 18:253] = (220, 180, 20)
    image[148:152, 18:252] = (220, 20, 20)
    image[159:172, 18:253] = (20, 40, 220)
    parsed = HUDParser.from_profile(PROFILE).parse(image)
    assert parsed.valid
    assert parsed.target_locked is False
    assert parsed.target_dead is False


def test_shifted_self_hud_without_target_stays_unlocked() -> None:
    strip = read_png(SHIFTED)
    image = np.full((2580, 4112, 3), 80, dtype=np.uint8)
    image[77:361, 0:280] = strip
    parsed = HUDParser.from_profile(PROFILE).parse(image)
    assert parsed.target_locked is False


def test_named_self_bars_still_win() -> None:
    parsed = HUDParser(_layout()).parse(_scene(hp=0.5, mp=1.0, cp=0.25, target=False))
    assert abs((parsed.self_hp_ratio or -1) - 0.5) <= 0.02


def test_target_absent_on_flat_panel() -> None:
    parsed = HUDParser(_layout()).parse(_scene(hp=1.0, mp=1.0, cp=1.0, target=False))
    assert parsed.valid
    assert parsed.target_locked is False
    assert parsed.target_hp_ratio is None


def test_contrast_without_red_is_not_a_target() -> None:
    image = _scene(hp=1.0, mp=1.0, cp=1.0, target=False)
    image[0:30, 100:200] = 70
    image[0, 100:200] = 230
    image[29, 100:200] = 230
    image[:, 100] = 230
    image[:, 199] = 230
    parsed = HUDParser(_layout()).parse(image)
    assert parsed.valid
    assert parsed.target_locked is False
    assert parsed.target_hp_ratio is None


def test_black_frame_is_invalid() -> None:
    parsed = HUDParser(_layout()).parse(np.zeros((32, 32, 3), dtype=np.uint8))
    assert parsed.valid is False
    assert parsed.reason == "black_or_folded"


def test_profile_loads() -> None:
    parser = HUDParser.from_profile(PROFILE)
    assert not parser.layout.self_bars.empty
    assert not parser.layout.target_frame.empty
    assert parser.layout.self_hp is not None
    assert parser.layout.target_hp is not None
    assert parser.layout.self_hp.pixel_box(4112, 2580) == (31, 151, 582, 155)
    assert parser.layout.self_mp.pixel_box(4112, 2580) == (31, 162, 582, 175)
    assert parser.layout.self_cp.pixel_box(4112, 2580) == (31, 130, 582, 135)
    assert parser.layout.target_hp.pixel_box(4112, 2580) == (2001, 139, 2711, 142)


def test_enlarged_live_self_status_is_read() -> None:
    path = ROOT / "docs" / "evidence" / "live-s4" / "client-reference-hod95.png"
    if not path.exists():
        return
    parsed = HUDParser.from_profile(PROFILE).parse(read_png(path))
    assert parsed.valid
    assert (parsed.self_hp_ratio or 0.0) > 0.9
    assert (parsed.self_mp_ratio or 0.0) > 0.9
    assert (parsed.self_cp_ratio or 0.0) > 0.9
    assert parsed.target_locked is False
    assert parsed.target_dead is False


def test_wide_target_bar_right_of_enlarged_self() -> None:
    image = np.full((2580, 4112, 3), 40, dtype=np.uint8)
    image[130:135, 31:582] = (220, 180, 20)
    image[151:155, 31:582] = (220, 20, 20)
    image[162:175, 31:582] = (20, 40, 220)
    image[118:138, 900:1700] = (50, 35, 25)
    image[124:132, 920:1680] = (220, 20, 20)
    parsed = HUDParser.from_profile(PROFILE).parse(image)
    assert (parsed.self_hp_ratio or 0.0) > 0.8
    assert parsed.target_locked is True
    assert (parsed.target_hp_ratio or 0.0) >= 0.15
    assert parsed.target_dead is False


def test_bridge_publishes_ui_vision() -> None:
    hub = TelemetryHub()
    bridge = VisionTelemetryBridge(hub)
    parsed = HUDParser(_layout()).parse(_scene(hp=0.8, mp=0.5, cp=0.5, target=True, target_hp=0.6))
    assert bridge.publish(parsed, now_ns=1_000_000) == 2
    health = hub.get_latest(HealthUpdate)
    target = hub.get_latest(TargetState)
    assert health is not None and health.source == "ui_vision" and health.is_self
    assert abs(health.current_hp - 80.0) <= 2.0
    assert health.max_hp == 100.0
    assert target is not None and target.source == "ui_vision" and target.locked
    assert target.target_id is None
    same = HUDParser(_layout()).parse(_scene(hp=0.8, mp=0.5, cp=0.5, target=True, target_hp=0.6))
    assert bridge.publish(same, now_ns=2_000_000) == 0
    assert len(hub) == 2


def test_bridge_ignores_invalid_frames() -> None:
    hub = TelemetryHub()
    bridge = VisionTelemetryBridge(hub)
    parsed = HUDParser(_layout()).parse(np.zeros((16, 16, 3), dtype=np.uint8))
    assert bridge.publish(parsed) == 0
    assert len(hub) == 0


def test_stale_flag_300ms() -> None:
    hub = TelemetryHub()
    parsed = HUDParser(_layout()).parse(_scene(hp=1.0, mp=1.0, cp=1.0, target=False))
    VisionTelemetryBridge(hub).publish(parsed, now_ns=0)
    event = hub.get_latest(HealthUpdate)
    assert event is not None
    assert hub.is_stale(event, threshold_ms=300, now_ns=400_000_000)
    assert not hub.is_stale(event, threshold_ms=300, now_ns=100_000_000)
