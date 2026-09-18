from pathlib import Path

import numpy as np

from l2_brain.bench.h8_latency_bench import percentile, run_h8_bench
from l2_brain.cli import main
from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster
from l2_brain.live.s4_probe import ScriptedGrabber
from l2_brain.vision.hud_parser import HUDParser, HudLayout


class _Clock:
    def __init__(self) -> None:
        self.t = 10**12

    def __call__(self) -> int:
        return self.t

    def advance_ms(self, ms: int) -> None:
        self.t += ms * 1_000_000


def _write_profile(path: Path) -> Path:
    HUDParser(
        HudLayout.from_mapping(
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
    )
    import json

    path.write_text(
        json.dumps(
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
        ),
        encoding="utf-8",
    )
    return path


def _frame() -> np.ndarray:
    image = np.full((64, 96, 3), 40, dtype=np.uint8)
    image[0:8, 0:40] = (220, 180, 20)
    image[8:16, 0:40] = (220, 20, 20)
    return image


def test_percentile_order() -> None:
    assert percentile([1, 2, 3, 4, 100], 0.95) >= 4.0


def test_flags_block_without_danger(tmp_path: Path) -> None:
    payload = run_h8_bench(
        live=True,
        danger_confirmed=False,
        samples=4,
        out_path=tmp_path / "blocked.json",
    )
    assert payload["aborted"] == "live_flags_required"
    assert payload["h8_closed"] is False
    assert payload["hid_sent"] is False


def test_cli_without_flags(tmp_path: Path) -> None:
    out = tmp_path / "cli.json"
    code = main(["bench-h8", "--samples", "4", "--out", str(out)])
    assert code == 2
    assert "live_flags_required" in out.read_text(encoding="utf-8")


def test_scripted_ticks_no_game_keys(tmp_path: Path) -> None:
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
    payload = run_h8_bench(
        live=True,
        danger_confirmed=True,
        samples=6,
        warmup=2,
        grabber=ScriptedGrabber([_frame()]),
        backend=backend,
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "h8.json",
        focus_probe=lambda: True,
    )
    assert payload["ok"] is True
    assert payload["aborted"] is None
    assert payload["h8"]["n"] == 6.0
    assert payload["pipeline"]["n"] == 6.0
    assert payload["h8_p95_ms"] is not None
    assert payload["hid_sent"] is False
    assert payload["stuck_keys_count"] == 0
    assert not any(c[0] == "key" for c in poster.calls)
    assert not any(c[0] == "mouse" for c in poster.calls)
    assert payload["farm"] is False
    for row in payload["samples"]:
        assert row["h8_ms"] == row["observe_ms"] + row["infer_ms"] + row["act_ms"]
        assert row["pipeline_ms"] == row["observe_ms"] + row["parse_ms"] + row["infer_ms"] + row["act_ms"]
