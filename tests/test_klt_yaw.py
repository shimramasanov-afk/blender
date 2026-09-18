from pathlib import Path
from unittest.mock import patch

import numpy as np

from l2_brain.calibration.klt_yaw import (
    KLTYaw,
    SEARCH,
    analysis_mask,
    coarse_shift,
    estimate_yaw_klt,
)
from l2_brain.calibration.motion_calibrator import (
    PROFILE_DX_MIN,
    run_klt_yaw_calibration,
    run_v3_yaw_calibration,
    v3_motion_block,
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


def _mid_scene(h: int = 300, w: int = 500, seed: int = 3, shift: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    image = np.full((h, w, 3), 18, dtype=np.uint8)
    y0, y1 = int(h * 0.30), int(h * 0.65)
    x0, x1 = int(w * 0.10), int(w * 0.90)
    hh, ww = y1 - y0, x1 - x0
    noise = rng.integers(40, 200, size=(hh, ww), dtype=np.uint8)
    band = noise
    for _ in range(70):
        yy = int(rng.integers(3, hh - 3))
        xx = int(rng.integers(3, ww - 3))
        band[yy - 2 : yy + 3, xx - 2 : xx + 3] = int(rng.integers(20, 255))
    image[y0:y1, x0:x1, 0] = band
    image[y0:y1, x0:x1, 1] = np.roll(band, 2, axis=1)
    image[y0:y1, x0:x1, 2] = np.roll(band, 3, axis=0)
    if shift:
        image = np.roll(image, int(shift), axis=1)
    image[int(h * 0.55) : int(h * 0.95), int(w * 0.42) : int(w * 0.58)] = 230
    return image


def _klt(median_dx: float, *, reliable: bool | None = None) -> KLTYaw:
    ok = bool(reliable if reliable is not None else abs(median_dx) >= 2.0)
    return KLTYaw(80, 80, 75, 70, 0.93, float(median_dx), 1.0, 0.2, ok, "ok" if ok else "shift_too_small")


def _stub_klt(moved: np.ndarray, dx: float):
    def _estimate(prev, curr, profile_path=None, seed=0):
        if curr is moved or np.array_equal(curr, moved):
            return _klt(dx)
        return _klt(0.0)

    return _estimate


def test_mask_drops_character_keeps_midplane() -> None:
    mask = analysis_mask(300, 500)
    assert bool(mask[100, 250])
    assert not bool(mask[200, 250])
    assert not bool(mask[20, 40])


def test_klt_recovers_horizontal_roll() -> None:
    prev = _mid_scene(shift=0)
    curr = _mid_scene(shift=10)
    est = estimate_yaw_klt(prev, curr, seed=0)
    assert est.total_features >= 30
    assert est.valid_inliers >= 30
    assert est.inlier_ratio >= 0.70
    assert abs(est.median_dx - 10.0) < 2.0
    assert est.reliable is True


def test_klt_flags_block(tmp_path: Path) -> None:
    payload = run_klt_yaw_calibration(
        live=True,
        danger_confirmed=False,
        out_path=tmp_path / "blocked.json",
        write_profile=False,
    )
    assert payload["aborted"] == "live_flags_required"
    assert payload["q5_closed"] is False
    assert payload["hid_sent"] is False


def test_cli_klt_without_flags(tmp_path: Path) -> None:
    out = tmp_path / "cli.json"
    code = main(["calibrate-motion", "--klt", "--out", str(out)])
    assert code == 2
    assert "live_flags_required" in out.read_text(encoding="utf-8")


def test_klt_scripted_right_left_symmetry(tmp_path: Path) -> None:
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
    idle = _mid_scene(shift=0)
    righted = _mid_scene(shift=-12)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            keys = [row.key for row in backend.log]
            if keys.count("left_arrow") >= 1:
                return idle
            if keys.count("right_arrow") >= 1:
                return righted
            return idle

    profile = tmp_path / "p.json"
    profile.write_text("{}", encoding="utf-8")
    payload = run_klt_yaw_calibration(
        live=True,
        danger_confirmed=True,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=profile,
        out_path=tmp_path / "klt.json",
        write_profile=True,
    )
    assert payload["ok"] is True
    assert payload["aborted"] is None
    assert payload["right"]["reliable"] is True
    assert payload["left"]["reliable"] is True
    assert payload["symmetry_ok"] is True
    assert payload["reliable"] is True
    assert payload["q5_closed"] is True
    assert payload.get("profile_written") == str(profile)
    written = profile.read_text(encoding="utf-8")
    assert "camera_deg_per_sec" in written
    assert "klt_ransac" in written
    keys = [c[1] for c in poster.calls if c[0] == "key"]
    assert 0x7C in keys
    assert 0x7B in keys
    assert 0x0D not in keys


def test_v3_flags_block(tmp_path: Path) -> None:
    payload = run_v3_yaw_calibration(
        live=True,
        danger_confirmed=False,
        out_path=tmp_path / "blocked.json",
        write_profile=False,
    )
    assert payload["aborted"] == "live_flags_required"
    assert payload["q5_closed"] is False
    assert payload["hid_sent"] is False
    assert payload["farm"] is False


def test_cli_rmb_without_flags(tmp_path: Path) -> None:
    out = tmp_path / "cli.json"
    code = main(["calibrate-motion", "--rmb", "--out", str(out)])
    assert code == 2
    assert "live_flags_required" in out.read_text(encoding="utf-8")


def test_v3_motion_block_gates() -> None:
    klt = {
        "reliable": True,
        "median_dx": 60.0,
        "valid_inliers": 40,
        "inlier_ratio": 0.8,
    }
    block = v3_motion_block(mechanism="rmb_drag", klt=klt, mouse_dx=150.0, frame_width=500)
    assert abs(block["px_cam_per_px_mouse"] - 0.4) < 1e-9
    assert abs(block["deg_per_mouse_px"] - 0.06) < 1e-9
    assert block["physical"] is True
    assert block["reliable"] is True
    assert block["q5_closed"] is True
    small = dict(klt, median_dx=40.0)
    mid = v3_motion_block(mechanism="rmb_drag", klt=small, mouse_dx=150.0, frame_width=500)
    assert mid["physical"] is True
    assert mid["reliable"] is False
    assert mid["q5_closed"] is True
    assert PROFILE_DX_MIN == 50.0
    only_coarse = v3_motion_block(
        mechanism="rmb_drag",
        klt={
            "reliable": True,
            "median_dx": 0.0,
            "valid_inliers": 40,
            "inlier_ratio": 0.95,
            "coarse_dx": 2000.0,
            "coarse_peak": 0.4,
            "coarse_physical": True,
        },
        mouse_dx=480.0,
        frame_width=4112,
    )
    assert only_coarse["physical"] is True
    assert only_coarse["klt_physical"] is False
    assert only_coarse["coarse_physical"] is True
    assert only_coarse["q5_closed"] is False
    assert only_coarse["reliable"] is False
    assert abs(only_coarse["assumed_yaw_deg"] - (2000.0 / 4112.0) * 75.0) < 1e-9


def test_coarse_shift_recovers_large_roll_klt_cannot() -> None:
    prev = _mid_scene(shift=0)
    curr = _mid_scene(shift=160)
    est = estimate_yaw_klt(prev, curr, seed=0)
    coarse = coarse_shift(prev, curr)
    assert SEARCH == 80
    assert abs(est.median_dx) < 30.0
    assert abs(float(coarse["coarse_dx"]) - 160.0) < 16.0
    assert float(coarse["pixel_diff_mean"]) > 8.0
    assert float(coarse["coarse_peak"]) >= 0.04


def test_v3_rmb_physical_writes_profile(tmp_path: Path) -> None:
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
    backend.window_origin = (0.0, 0.0)
    backend.window_size = (500.0, 300.0)
    idle = _mid_scene(shift=0)
    moved = _mid_scene(shift=8)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            if any(c[0] == "mouse" and c[1] == 7 for c in poster.calls):
                return moved
            return idle

    profile = tmp_path / "p.json"
    profile.write_text("{}", encoding="utf-8")
    with patch("l2_brain.calibration.motion_calibrator.estimate_yaw_klt", _stub_klt(moved, 60.0)):
        payload = run_v3_yaw_calibration(
            live=True,
            danger_confirmed=True,
            grabber=_Aware([idle]),
            backend=backend,
            sleeper=lambda s: clock.advance_ms(int(s * 1000)),
            now_ns=clock,
            profile_path=profile,
            out_path=tmp_path / "v3.json",
            write_profile=True,
        )
    assert payload["ok"] is True
    assert payload["aborted"] is None
    assert payload["mechanism"] == "rmb_drag"
    assert payload["physical"] is True
    assert payload["q5_closed"] is True
    assert payload["valid_inliers"] >= 30
    assert abs(float(payload["median_dx"]) - 60.0) < 3.0
    assert payload.get("profile_written") == str(profile)
    assert "px_cam_per_px_mouse" in profile.read_text(encoding="utf-8")
    assert not any(c[0] == "key" for c in poster.calls)
    assert not any(c[1] == 0x7C for c in poster.calls if c[0] == "key")


def test_v3_rmb_miss_falls_back_to_pulse(tmp_path: Path) -> None:
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
    idle = _mid_scene(shift=0)
    moved = _mid_scene(shift=8)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            keys = [row.key for row in backend.log]
            if keys.count("right_arrow") >= 1:
                return moved
            return idle

    profile = tmp_path / "p.json"
    profile.write_text("{}", encoding="utf-8")
    with patch("l2_brain.calibration.motion_calibrator.estimate_yaw_klt", _stub_klt(moved, 55.0)):
        payload = run_v3_yaw_calibration(
            live=True,
            danger_confirmed=True,
            grabber=_Aware([idle]),
            backend=backend,
            sleeper=lambda s: clock.advance_ms(int(s * 1000)),
            now_ns=clock,
            profile_path=profile,
            out_path=tmp_path / "v3-pulse.json",
            write_profile=True,
        )
    assert payload["ok"] is True
    assert payload["mechanism"] == "arrow_pulse"
    assert payload["physical"] is True
    assert payload["q5_closed"] is True
    assert any(c[0] == "mouse" and c[1] == 3 for c in poster.calls)
    assert any(c == ("key", 0x7C, True, 4242) for c in poster.calls)
    assert payload.get("profile_written") == str(profile)
