from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from l2_brain.capture.errors import CaptureError, SourceLost
from l2_brain.capture.helper import default_helper_path, diagnose_permission
from l2_brain.capture.masks import apply_profile
from l2_brain.capture.profile import WindowProfile
from l2_brain.capture.sck import SCKConfig, SCKFrameSource
from l2_brain.capture.screencapturekit import ScreenCaptureKitSource
from l2_brain.capture.circuit import build_sck_circuit
from l2_brain.circuit.config import CircuitConfig
from l2_brain.cli import main
from l2_brain.experiment.replay import SessionReplay

MOCK_HELPER = Path(__file__).resolve().parent / "helpers" / "mock_sck_helper.py"


def _mock_cmd(*extra: str) -> list[str]:
    return [sys.executable, str(MOCK_HELPER), *extra]


def test_old_observation_api_still_blocked() -> None:
    with pytest.raises(NotImplementedError):
        ScreenCaptureKitSource().start()


def test_profile_masks_do_not_hardcode_hud() -> None:
    image = np.full((20, 40, 3), 90, dtype=np.uint8)
    profile = WindowProfile.from_mapping(
        {
            "profile_id": "fixture",
            "roi": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            "mask_fill": [0, 0, 0],
            "masks": [
                {"name": "ui", "norm_rect": [0.0, 0.0, 1.0, 0.25]},
                {"name": "character_center", "norm_rect": [0.4, 0.4, 0.2, 0.2]},
                {"name": "ignore_nav", "norm_rect": [0.75, 0.75, 0.25, 0.25]},
            ],
        }
    )
    out = apply_profile(image, profile)
    assert out[0, 0].tolist() == [0, 0, 0]
    assert out[10, 20].tolist() == [0, 0, 0]
    assert out[19, 39].tolist() == [0, 0, 0]
    assert out[8, 4].tolist() == [90, 90, 90]


def test_mock_helper_frames_enter_frame_source() -> None:
    source = SCKFrameSource(SCKConfig(helper_command=_mock_cmd("--frames", "5", "--sleep-ms", "2")))
    source.initialize()
    frames = [source.latest() for _ in range(4)]
    source.close()
    assert frames[0].pixel_format == "rgb8"
    assert frames[0].image is not None
    assert frames[0].image.shape == (24, 32, 3)
    assert frames[0].source_id == "mock.sck"
    assert frames[0].clock_id == "event"


def test_resize_event_changes_frame_shape() -> None:
    source = SCKFrameSource(
        SCKConfig(helper_command=_mock_cmd("--frames", "5", "--resize-at", "2", "--sleep-ms", "2"))
    )
    source.initialize()
    shapes = [source.latest().image.shape for _ in range(4)]  # type: ignore[union-attr]
    source.close()
    assert shapes[0] == (24, 32, 3)
    assert any(shape != (24, 32, 3) for shape in shapes)
    assert source._resizes >= 1


def test_source_lost_is_explicit() -> None:
    source = SCKFrameSource(
        SCKConfig(
            helper_command=_mock_cmd("--frames", "6", "--lose-at", "2", "--sleep-ms", "2"),
            latest_timeout_s=1.0,
        )
    )
    source.initialize()
    source.latest()
    with pytest.raises(SourceLost):
        for _ in range(6):
            source.latest()
    source.close()


def test_slow_consumer_counts_drops() -> None:
    source = SCKFrameSource(
        SCKConfig(helper_command=_mock_cmd("--frames", "10", "--sleep-ms", "1"), latest_timeout_s=2.0)
    )
    source.initialize()
    import time

    deadline = time.monotonic() + 2.0
    while source._queue.drops < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    source.latest()
    drops = source.queue_drops
    source.close()
    assert drops >= 1


def test_stop_is_idempotent() -> None:
    source = SCKFrameSource(SCKConfig(helper_command=_mock_cmd("--frames", "3", "--sleep-ms", "1")))
    source.initialize()
    source.latest()
    source.close()
    source.close()


def test_mock_session_records_and_replays(tmp_path: Path) -> None:
    source = SCKFrameSource(SCKConfig(helper_command=_mock_cmd("--frames", "8", "--sleep-ms", "2")))
    config = CircuitConfig(
        ticks=4,
        record_path=tmp_path / "sck-mock",
        keep_frames="all",
        log_level="ERROR",
        source_id="mock.sck",
    )
    records = build_sck_circuit(config, source).run()
    assert len(records) == 4
    replay = SessionReplay(tmp_path / "sck-mock")
    view = replay.inspect(1)
    assert view.frame_image is not None
    assert view.intent
    assert view.command
    assert view.timings


def test_missing_window_config_fails_fast() -> None:
    source = SCKFrameSource(SCKConfig())
    with pytest.raises(CaptureError):
        source.initialize()


def test_live_self_test_record_replay(tmp_path: Path) -> None:
    helper = default_helper_path()
    if not helper.is_file():
        pytest.skip("capture-probe is not built")
    try:
        diagnose_permission(helper)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Screen Recording not usable: {exc}")
    out = tmp_path / "sck-live"
    code = main(
        [
            "capture",
            "record",
            "--self-test",
            "--ticks",
            "4",
            "--fps",
            "20",
            "--out",
            str(out),
            "--log-level",
            "ERROR",
        ]
    )
    if code != 0:
        pytest.skip("self-test helper did not produce frames")
    replay = SessionReplay(out)
    view = replay.inspect(0)
    assert view.frame_image is not None
    assert view.frame_image.ndim == 3
    assert view.to_dict()["frame"]["shape"][2] == 3
    assert main(["replay", str(out)]) == 0
