from pathlib import Path

import numpy as np

from l2_brain.calibration.motion_calibrator import (
    center_crop,
    horizon_crop,
    maybe_write_profile_if_gates,
    phase_shift,
    run_motion_calibration,
    yaw_deg_per_sec,
)
from l2_brain.cli import main
from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster
from l2_brain.live.s4_probe import ScriptedGrabber


class _Clock:
    def __init__(self) -> None:
        self.t = 10**12

    def __call__(self) -> int:
        return self.t

    def advance_ms(self, ms: int) -> None:
        self.t += ms * 1_000_000


def _texture(h: int = 80, w: int = 120, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.integers(20, 200, size=(h, w), dtype=np.uint8)
    image = np.stack([base, np.roll(base, 3, axis=1), np.roll(base, 5, axis=0)], axis=-1)
    return image


def test_phase_shift_recovers_horizontal_roll() -> None:
    src = _texture()
    moved = np.roll(src, 12, axis=1)
    dx, dy, peak = phase_shift(src, moved)
    assert abs(dx - 12.0) < 0.6
    assert abs(dy) < 0.6
    assert peak > 0.01


def test_yaw_uses_full_frame_width_not_crop() -> None:
    deg = yaw_deg_per_sec(41.12, 4112, 500, fov_deg=75.0)
    assert abs(deg - 1.5) < 1e-9


def test_center_crop_is_centered() -> None:
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    image[35:65, 75:125] = 255
    crop = center_crop(image, 50, 30)
    assert crop.shape[0] == 30
    assert crop.shape[1] == 50
    assert int(crop.mean()) > 100


def test_flags_block_without_danger(tmp_path: Path) -> None:
    payload = run_motion_calibration(
        live=True,
        danger_confirmed=False,
        out_path=tmp_path / "blocked.json",
        write_profile=False,
    )
    assert payload["aborted"] == "live_flags_required"
    assert payload["hid_sent"] is False
    assert payload["h8_closed"] is False


def test_cli_without_flags(tmp_path: Path) -> None:
    out = tmp_path / "cli.json"
    code = main(["calibrate-motion", "--out", str(out)])
    assert code == 2
    assert "live_flags_required" in out.read_text(encoding="utf-8")


def test_scripted_shift_and_step(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=poster,
        focus_probe=lambda: True,
        now_ns=clock,
    )
    idle = _texture(300, 500, seed=2)
    yawed = np.roll(idle, 8, axis=1)
    walked = np.roll(yawed, 6, axis=0)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            keys = [row.key for row in backend.log]
            if keys.count("w") >= 1:
                return walked
            if keys.count("right_arrow") >= 1:
                return yawed
            return idle

    profile = tmp_path / "hud.json"
    profile.write_text("{}", encoding="utf-8")
    payload = run_motion_calibration(
        live=True,
        danger_confirmed=True,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=profile,
        out_path=tmp_path / "cal.json",
        write_profile=True,
    )
    assert payload["ok"] is True
    assert payload["aborted"] is None
    assert payload["motion_detected"] is True
    assert payload["yaw_shift_px"] is not None
    assert abs(float(payload["yaw_shift_px"]) - 8.0) < 1.0
    assert payload["deg_per_sec"] is not None
    assert payload["stuck_keys_count"] == 0
    assert payload["watchdog_tripped"] is False
    assert payload["h8_closed"] is False
    assert payload["session_ms"] < 8000
    assert not any(c[0] == "mouse" for c in poster.calls)
    keys = [c[1] for c in poster.calls if c[0] == "key"]
    assert 0x7C in keys
    assert 0x0D in keys
    written = profile.read_text(encoding="utf-8")
    assert "keyboard_arrow" in written
    assert "yaw_from_assumed_fov" in written


def _horizon_scene(shift: int = 0, *, character: bool = True) -> np.ndarray:
    h, w = 200, 400
    image = np.zeros((h, w, 3), dtype=np.uint8)
    sky = np.zeros((30, w), dtype=np.uint8)
    xs = np.arange(w, dtype=np.int32)
    sky[:, :] = (80 + (xs * 3) % 140).astype(np.uint8)
    sky = np.roll(sky, shift, axis=1)
    image[30:60, :, 0] = sky
    image[30:60, :, 1] = np.roll(sky, 4, axis=1)
    image[30:60, :, 2] = np.roll(sky, 7, axis=1)
    if character:
        image[80:150, 170:230] = 210
    return image


def test_horizon_crop_skips_center_character() -> None:
    image = _horizon_scene()
    crop = horizon_crop(image)
    assert crop.shape[0] == 30
    assert crop.shape[1] == 200
    assert float(image[80:150, 170:230].mean()) > 200
    assert float(crop.mean()) < 160


def test_horizon_shift_survives_center_character() -> None:
    prev = _horizon_scene(0)
    curr = _horizon_scene(14)
    dx_h, _, peak_h = phase_shift(horizon_crop(prev), horizon_crop(curr))
    dx_c, _, _peak_c = phase_shift(center_crop(prev, 160, 80), center_crop(curr, 160, 80))
    assert abs(dx_h - 14.0) < 1.0
    assert peak_h >= 0.15
    assert abs(dx_c) < 2.0


def test_horizon_run_skips_walk_and_marks_unreliable(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=poster,
        focus_probe=lambda: True,
        now_ns=clock,
    )
    idle = np.full((80, 120, 3), 30, dtype=np.uint8)
    profile = tmp_path / "hud.json"
    profile.write_text("{}", encoding="utf-8")
    payload = run_motion_calibration(
        live=True,
        danger_confirmed=True,
        band="horizon",
        skip_walk=True,
        grabber=ScriptedGrabber([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=profile,
        out_path=tmp_path / "v2.json",
        write_profile=True,
    )
    assert payload["ok"] is True
    assert payload["crop_band"] == "horizon"
    assert payload["peak_reliable"] is False
    assert payload["q5_horizon_ok"] is False
    assert payload["q5_closed"] is False
    assert "w" not in [row.key for row in backend.log]
    assert payload.get("profile_written") is None


def test_profile_gate_needs_both_h8_and_peak(tmp_path: Path) -> None:
    profile = tmp_path / "p.json"
    profile.write_text("{}", encoding="utf-8")
    motion = {"yaw_peak": 0.2, "crop_band": "horizon"}
    assert maybe_write_profile_if_gates(profile, h8_p95_ms=80.0, yaw_peak=0.2, motion=motion) is True
    assert maybe_write_profile_if_gates(profile, h8_p95_ms=120.0, yaw_peak=0.2, motion=motion) is False
    assert maybe_write_profile_if_gates(profile, h8_p95_ms=80.0, yaw_peak=0.05, motion=motion) is False


def test_cli_horizon_without_flags(tmp_path: Path) -> None:
    out = tmp_path / "cli-h.json"
    code = main(["calibrate-motion", "--horizon", "--out", str(out)])
    assert code == 2
    assert "live_flags_required" in out.read_text(encoding="utf-8")
