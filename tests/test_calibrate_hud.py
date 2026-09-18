from pathlib import Path

import numpy as np

from l2_brain.capture.profile import NormRect
from l2_brain.vision.calibrate_hud import overlay_hud, read_png, write_png
from l2_brain.vision.hud_parser import HUDParser, HudLayout

ACTIVE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "live-s4" / "interlude-target-active.png"
PROFILE = Path(__file__).resolve().parents[1] / "config" / "window_profiles" / "parallels_l2.json"


def test_overlay_marks_named_roi(tmp_path: Path) -> None:
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    layout = HudLayout.from_mapping(
        {
            "hud": {
                "self_bars": {"norm_rect": [0.0, 0.0, 0.5, 0.2]},
                "self_hp": {"norm_rect": [0.0, 0.05, 0.5, 0.05]},
                "target_frame": {"norm_rect": [0.5, 0.0, 0.4, 0.2]},
            }
        }
    )
    out = overlay_hud(image, layout)
    assert out[1, 1].tolist() != [0, 0, 0]
    path = tmp_path / "x.png"
    write_png(path, out)
    assert path.stat().st_size > 32
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_roundtrip(tmp_path: Path) -> None:
    image = np.zeros((12, 16, 3), dtype=np.uint8)
    image[3:9, 4:12] = (220, 40, 30)
    path = tmp_path / "round.png"
    write_png(path, image)
    back = read_png(path)
    assert back.shape == image.shape
    assert np.array_equal(back, image)


def test_pixel_box_survives_norm() -> None:
    rect = NormRect.from_pixel_box(316, 205, 404, 211, 4112, 2580)
    assert rect.pixel_box(4112, 2580) == (316, 205, 404, 211)


def test_recorded_interlude_status_and_target() -> None:
    if not ACTIVE.exists():
        return
    parsed = HUDParser.from_profile(PROFILE).parse(read_png(ACTIVE))
    assert parsed.valid
    assert parsed.target_locked is True
    assert abs((parsed.self_hp_ratio or -1) - 1.0) <= 0.08
    assert abs((parsed.self_mp_ratio or -1) - 1.0) <= 0.08
    assert abs((parsed.self_cp_ratio or -1) - 1.0) <= 0.08
    assert (parsed.target_hp_ratio or 0.0) > 0.0
