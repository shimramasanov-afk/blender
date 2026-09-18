from l2_brain.capture.h7 import h7_verdict, is_black_frame, resolve_visible_window
import numpy as np


def test_black_frame_detects_empty() -> None:
    dark = np.zeros((8, 8, 3), dtype=np.uint8)
    lit = np.full((8, 8, 3), 40, dtype=np.uint8)
    assert is_black_frame(dark)
    assert not is_black_frame(lit)


def test_h7_verdict_thresholds() -> None:
    ok = h7_verdict(median_interval_ms=40.0, drop_rate=0.02, black_rate=0.01)
    assert ok["h7_accepted"] is True
    assert ok["h7_status"] == "accepted"
    mid = h7_verdict(median_interval_ms=60.0, drop_rate=0.02, black_rate=0.01)
    assert mid["h7_accepted"] is False
    assert mid["h7_status"] == "not_accepted"
    bad = h7_verdict(median_interval_ms=90.0, drop_rate=0.0, black_rate=0.0)
    assert bad["h7_status"] == "rejected"
    black = h7_verdict(median_interval_ms=40.0, drop_rate=0.0, black_rate=0.15)
    assert black["h7_status"] == "rejected"


def test_resolve_visible_window_by_title() -> None:
    windows = [
        {"id": 1, "on_screen": True, "title": "Chrome", "bundle": "com.google.Chrome", "height": 800},
        {
            "id": 13745,
            "on_screen": True,
            "title": "Windows 11",
            "bundle": "com.parallels.desktop.console",
            "height": 1290,
        },
        {
            "id": 13747,
            "on_screen": True,
            "title": "",
            "bundle": "com.parallels.desktop.console",
            "height": 54,
        },
    ]
    found = resolve_visible_window(
        windows,
        window_id=999,
        title="Windows 11",
        bundle_id="com.parallels.desktop.console",
    )
    assert found is not None
    assert found["id"] == 13745
