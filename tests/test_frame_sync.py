from pathlib import Path
from unittest.mock import patch

import numpy as np

from l2_brain.calibration.frame_sync import (
    analysis_crop,
    grab_shot,
    pixel_diff_mean,
    wait_unique_frame,
    write_png,
)
from l2_brain.calibration.klt_yaw import KLTYaw
from l2_brain.calibration.motion_calibrator import run_sync_diag_calibration
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


def test_grab_shot_is_deep_copy() -> None:
    src = np.zeros((8, 8, 3), dtype=np.uint8)
    src[2, 2] = 9

    class _Once:
        def latest_image(self) -> np.ndarray:
            return src

    image, ts = grab_shot(_Once())
    assert ts == 0
    assert not np.shares_memory(image, src)
    src[2, 2] = 0
    assert int(image[2, 2, 0]) == 9


def test_pixel_diff_and_png(tmp_path: Path) -> None:
    a = np.zeros((20, 20, 3), dtype=np.uint8)
    b = a.copy()
    b[5, 5] = 10
    assert pixel_diff_mean(a, a) == 0.0
    assert pixel_diff_mean(a, b) > 0.0
    path = tmp_path / "x.png"
    write_png(path, analysis_crop(np.full((40, 40, 3), 7, dtype=np.uint8)))
    assert path.stat().st_size > 20
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_wait_unique_frame_skips_stale() -> None:
    clock = _Clock()
    stamps = [1000]

    def grab() -> tuple[np.ndarray, int]:
        stamps[0] += 40
        return np.zeros((4, 4, 3), dtype=np.uint8), stamps[0]

    image, ts, unique = wait_unique_frame(
        grab,
        1000,
        80,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        settle_s=0.3,
        max_wait_s=1.0,
        poll_s=0.0,
    )
    assert unique is True
    assert ts > 1080
    assert image.shape == (4, 4, 3)


def test_sync_diag_flags_block(tmp_path: Path) -> None:
    payload = run_sync_diag_calibration(
        live=True,
        danger_confirmed=False,
        out_path=tmp_path / "blocked.json",
        dump_dir=tmp_path,
        write_profile=False,
    )
    assert payload["aborted"] == "live_flags_required"
    assert payload["q5_closed"] is False
    assert payload["hid_sent"] is False


def test_cli_sync_diag_without_flags(tmp_path: Path) -> None:
    out = tmp_path / "cli.json"
    code = main(["calibrate-motion", "--sync-diag", "--out", str(out)])
    assert code == 2
    assert "live_flags_required" in out.read_text(encoding="utf-8")


def test_sync_diag_identical_frames(tmp_path: Path) -> None:
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
    idle = np.full((80, 120, 3), 18, dtype=np.uint8)
    payload = run_sync_diag_calibration(
        live=True,
        danger_confirmed=True,
        grabber=ScriptedGrabber([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=tmp_path / "p.json",
        out_path=tmp_path / "sync.json",
        dump_dir=tmp_path,
        write_profile=False,
    )
    assert payload["identical_frames_error"] is True
    assert payload["aborted"] == "identical_frames_error"
    assert payload["q5_closed"] is False


def test_sync_diag_rmb_hold_then_klt(tmp_path: Path) -> None:
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
    backend.window_size = (200.0, 100.0)
    idle = np.full((80, 120, 3), 18, dtype=np.uint8)
    moved = idle.copy()
    moved[:, 40:80] = 200

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            if any(c[0] == "mouse" and c[1] == 7 for c in poster.calls):
                return moved
            return idle

    def _klt(prev, curr, profile_path=None, seed=0):
        if curr.mean() > 50:
            return KLTYaw(80, 80, 75, 70, 0.93, 60.0, 1.0, 0.2, True, "ok")
        return KLTYaw(80, 80, 75, 70, 0.93, 0.0, 0.2, 0.1, False, "shift_too_small")

    profile = tmp_path / "p.json"
    profile.write_text("{}", encoding="utf-8")
    with patch("l2_brain.calibration.motion_calibrator.estimate_yaw_klt", _klt):
        payload = run_sync_diag_calibration(
            live=True,
            danger_confirmed=True,
            grabber=_Aware([idle]),
            backend=backend,
            sleeper=lambda s: clock.advance_ms(int(s * 1000)),
            now_ns=clock,
            profile_path=profile,
            out_path=tmp_path / "sync.json",
            dump_dir=tmp_path,
            write_profile=True,
        )
    assert payload["ok"] is True
    assert payload["identical_frames_error"] is False
    assert payload["mechanism"] == "rmb_drag_hold"
    assert payload["diff_mean"] and payload["diff_mean"] > 0.0
    assert payload["unique_frame"] is True
    assert payload["shares_memory"] is False
    assert payload["klt_median_dx"] == 60.0
    assert payload["q5_closed"] is True
    assert payload.get("profile_written") == str(profile)
    assert (tmp_path / "calibration_t0.png").is_file()
    assert (tmp_path / "calibration_t1.png").is_file()
    reasons = [c[1] for c in poster.calls if c[0] == "mouse"]
    assert 3 in reasons and 7 in reasons and 4 in reasons
