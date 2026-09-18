from pathlib import Path

import numpy as np

from l2_brain.bench.live_motion_probe import flow_magnitude_midnear, run_live_motion_probe
from l2_brain.cli import main
from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster
from l2_brain.live.s4_probe import ScriptedGrabber
from l2_brain.vision.flow import FlowField


class _Clock:
    def __init__(self) -> None:
        self.t = 10**12

    def __call__(self) -> int:
        return self.t

    def advance_ms(self, ms: int) -> None:
        self.t += ms * 1_000_000


def _texture(h: int = 64, w: int = 96, seed: int = 4, zoom: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.integers(30, 220, size=(h, w), dtype=np.uint8)
    for _ in range(40):
        yy = int(rng.integers(4, h - 4))
        xx = int(rng.integers(4, w - 4))
        base[yy - 3 : yy + 4, xx - 3 : xx + 4] = int(rng.integers(20, 255))
    if abs(zoom - 1.0) > 1e-6:
        nh = min(h, max(8, int(round(h / zoom))))
        nw = min(w, max(8, int(round(w / zoom))))
        y0, x0 = (h - nh) // 2, (w - nw) // 2
        crop = base[y0 : y0 + nh, x0 : x0 + nw]
        ys = np.linspace(0, crop.shape[0] - 1, h).astype(np.int32)
        xs = np.linspace(0, crop.shape[1] - 1, w).astype(np.int32)
        base = crop[ys][:, xs]
    return np.stack([base, np.roll(base, 2, axis=1), np.roll(base, 3, axis=0)], axis=-1)


def test_flow_magnitude_uses_midnear_band() -> None:
    ys = np.tile(np.linspace(2, 30, 6)[:, None], (1, 8)).astype(np.float32)
    xs = np.tile(np.linspace(2, 40, 8)[None, :], (6, 1)).astype(np.float32)
    u = np.where(ys >= 0.45 * 30.0, 4.0, 0.0).astype(np.float32)
    v = np.zeros_like(u)
    field = FlowField(
        u=u,
        v=v,
        confidence=np.ones_like(u),
        weak_texture=np.zeros_like(u, dtype=bool),
        xs=xs,
        ys=ys,
    )
    assert abs(flow_magnitude_midnear(field, 0.45) - 4.0) < 1e-5


def test_flags_block(tmp_path: Path) -> None:
    payload = run_live_motion_probe(
        live=True,
        danger_confirmed=False,
        out_path=tmp_path / "blocked.json",
        free_ticks=1,
        blocked_ticks=1,
    )
    assert payload["aborted"] == "live_flags_required"
    assert payload["hid_sent"] is False
    assert payload["stuck_detected"] is False
    assert payload["farm"] is False
    assert payload["frozen_l1_untouched"] is True


def test_cli_without_flags(tmp_path: Path) -> None:
    out = tmp_path / "cli.json"
    code = main(["live-motion", "--out", str(out)])
    assert code == 2
    assert "live_flags_required" in out.read_text(encoding="utf-8")


def test_scripted_free_vs_blocked_ratio(tmp_path: Path) -> None:
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
    idle = _texture(zoom=1.0)
    samples = {"n": 0}

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            # settle 0.05s runs once per tick; n is the current sample index.
            n = samples["n"]
            if n <= 0:
                return idle
            if n == 1:
                return _texture(zoom=1.12)
            return _texture(zoom=1.24)

    def sleeper(seconds: float) -> None:
        if seconds >= 0.04:
            samples["n"] += 1
        clock.advance_ms(int(seconds * 1000))

    payload = run_live_motion_probe(
        live=True,
        danger_confirmed=True,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=sleeper,
        now_ns=clock,
        profile_path=tmp_path / "missing.json",
        out_path=tmp_path / "flow.json",
        free_ticks=2,
        blocked_ticks=2,
        hold_ms=50,
    )
    assert payload["ok"] is True
    assert payload["aborted"] is None
    assert payload["hold_mode"] == "continuous"
    assert payload["flow_free_motion"] is not None
    assert payload["flow_blocked"] is not None
    assert float(payload["flow_free_motion"]) > float(payload["flow_blocked"])
    keys = [c for c in poster.calls if c[0] == "key"]
    downs = [c for c in keys if c == ("key", 0x0D, True, 4242)]
    ups = [c for c in keys if c == ("key", 0x0D, False, 4242)]
    assert len(downs) == 1
    assert len(ups) >= 1
    assert payload["encode"]["n"] == 4.0
    assert payload["farm"] is False
    assert payload["stuck_keys_count"] == 0
