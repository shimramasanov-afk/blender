from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from l2_brain.circuit.config import CircuitConfig
from l2_brain.circuit.loop import build_mock_circuit
from l2_brain.cli import main
from l2_brain.contracts import Frame
from l2_brain.experiment.clocks import ClockMismatch, ClockOffset, convert, interval_ms, stamp
from l2_brain.experiment.identity import OFFLINE_REPLAY_LIMIT
from l2_brain.experiment.queues import AsyncWriter, LatestOnlyQueue
from l2_brain.experiment.replay import SessionReplay
from l2_brain.experiment.timing import (
    bench_single_step_latency,
    bench_throughput,
    gpu_synchronize,
    measure_compute,
    summarize_series,
)


def test_clocks_refuse_mixed_domains() -> None:
    mono = stamp(10, "mono")
    event = stamp(20, "event")
    with pytest.raises(ClockMismatch):
        interval_ms(mono, event)
    converted = convert(event, ClockOffset(source="event", target="mono", add_ns=-5))
    assert interval_ms(mono, converted) == 5 / 1_000_000.0


def test_timing_report_has_percentiles_and_count() -> None:
    report = summarize_series([1.0, 2.0, 3.0, 4.0, 100.0], unit="ms")
    payload = report.to_dict()
    assert payload["n"] == 5
    assert payload["p50"] == 3.0
    assert payload["p95"] > payload["p50"]
    assert payload["p99"] >= payload["p95"]
    assert payload["unit"] == "ms"


def test_unsynced_gpu_is_not_compute_time() -> None:
    sync = gpu_synchronize()
    measured = measure_compute(lambda: 7, require_gpu_sync=True)
    assert measured.value == 7
    if sync.ok:
        assert measured.is_compute is True
        assert measured.synced is True
    else:
        assert measured.synced is False
        assert measured.is_compute is False
        with pytest.raises(RuntimeError, match="unsynced"):
            bench_single_step_latency(lambda: None, n=1, require_gpu_sync=True)


def test_latency_and_throughput_are_separate() -> None:
    latency = bench_single_step_latency(lambda: sum(range(32)), n=8)
    throughput = bench_throughput(lambda: sum(range(32)), n=8)
    assert latency.n == 8
    assert "p50" in latency.to_dict()
    assert throughput["kind"] == "throughput"
    assert throughput["not_latency"] is True
    assert throughput["n"] == 8
    assert throughput["items_per_s"] > 0


def test_latest_only_queue_prefers_fresh_frame() -> None:
    box: LatestOnlyQueue[int] = LatestOnlyQueue()
    box.put(1)
    box.put(2)
    box.put(3)
    assert box.take() == 3
    assert box.drops == 2
    assert box.stats["puts"] == 3


def test_async_writer_does_not_lose_on_close(tmp_path: Path) -> None:
    path = tmp_path / "out.jsonl"
    writer = AsyncWriter(path, maxsize=32)
    for i in range(10):
        writer.put({"kind": "tick", "i": i})
    writer.close()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["i"] for row in rows] == list(range(10))
    assert writer.dropped == 0


def test_async_writer_counts_drops_when_bounded(tmp_path: Path) -> None:
    path = tmp_path / "drop.jsonl"
    writer = AsyncWriter(path, maxsize=1)
    original = writer._emit

    def slow(item: object) -> None:
        time.sleep(0.01)
        original(item)

    writer._emit = slow  # type: ignore[method-assign]
    for i in range(12):
        writer.put({"kind": "tick", "i": i})
    writer.close()
    lines = [row for row in path.read_text(encoding="utf-8").splitlines() if row.strip()]
    assert writer.dropped >= 1
    assert writer.dropped + len(lines) == 12


def test_session_inspect_shows_frame_intent_command_timings(tmp_path: Path) -> None:
    root = tmp_path / "exp"
    config = CircuitConfig(
        seed=2,
        ticks=6,
        record_path=root,
        keep_frames="all",
        log_level="ERROR",
        model_version="feature_reactive:test",
    )
    records = build_mock_circuit(config).run()
    assert (root / "manifest.json").is_file()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == 2
    assert manifest["extras"]["code"]["package_version"]
    assert manifest["extras"]["model_version"] == "feature_reactive:test"
    replay = SessionReplay(root)
    view = replay.inspect(3)
    assert view.frame_image is not None
    assert view.frame_image.shape[2] == 3
    assert view.features["confidence"] >= 0.0
    assert "turn" in view.intent
    assert "issued_at_ns" in view.command
    assert view.timings["interval_clock"] == "mono"
    assert view.timings["frame_age_ms"] is not None
    assert view.timings["frame_age_ms"] >= 0.0
    assert view.timings["wait_frame_ms"] >= 0.0
    assert view.timings["encode_ms"] >= 0.0
    assert view.timings["infer_ms"] >= 0.0
    assert view.telemetry[0]["event_type"] == "mock.heartbeat"
    assert records[3].diagnostics is not None
    payload = view.to_dict()
    assert "offline_replay_limitation" in payload
    assert view.frame_sha256 is not None


def test_keep_every_other_frame(tmp_path: Path) -> None:
    root = tmp_path / "every"
    config = CircuitConfig(
        seed=0,
        ticks=4,
        record_path=root,
        keep_frames="every",
        frame_every=2,
        log_level="ERROR",
    )
    build_mock_circuit(config).run()
    names = sorted(p.name for p in (root / "frames").glob("*.npy"))
    assert names == ["000000.npy", "000002.npy"]


def test_step_and_speed_replay(tmp_path: Path) -> None:
    root = tmp_path / "play"
    build_mock_circuit(
        CircuitConfig(seed=1, ticks=4, record_path=root, keep_frames="all", log_level="ERROR")
    ).run()
    replay = SessionReplay(root)
    first = replay.step()
    second = replay.step()
    assert second.tick == first.tick + 1
    played = list(replay.play(speed=0.0, sleep=False, mode="speed"))
    assert len(played) == 4
    assert OFFLINE_REPLAY_LIMIT in replay.limitation()


def test_inject_drops_stale_frames() -> None:
    config = CircuitConfig(ticks=1, log_level="ERROR")
    circuit = build_mock_circuit(config)
    circuit.initialize()
    circuit.reset_episode(0)
    image = np.zeros((config.frame_h, config.frame_w, 3), dtype=np.uint8)
    image[10:20, 10:20] = (220, 36, 36)

    def _frame(frame_id: int) -> Frame:
        return Frame(
            frame_id=frame_id,
            timestamp_capture_ns=1,
            timestamp_received_ns=2,
            width=config.frame_w,
            height=config.frame_h,
            pixel_format="rgb8",
            source_id="mock.blob",
            image=image,
        )

    circuit.frames.inject(_frame(1))
    circuit.frames.inject(_frame(2))
    record = circuit.step()
    assert record.frame_id == 2
    assert record.diagnostics is not None
    assert record.diagnostics["frame_queue_drops"] == 1
    circuit.close()


def test_cli_inspect_and_offline_limitation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "cli-exp"
    assert main(["record", "--ticks", "3", "--seed", "4", "--out", str(root), "--log-level", "ERROR"]) == 0
    capsys.readouterr()
    assert main(["inspect", str(root), "--tick", "1"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["tick"] == 1
    assert inspected["frame"]["shape"][2] == 3
    assert "intent" in inspected
    assert "command" in inspected
    assert "timings" in inspected
    assert inspected["offline_replay_limitation"]
    assert main(["replay", str(root)]) == 0
    replayed = json.loads(capsys.readouterr().out)
    assert replayed["offline_replay"] is True
    assert replayed["closed_loop"] is False
    assert "changed future frames" in replayed["limitation"]
    assert main(["replay", str(root), "--mode", "speed", "--speed", "0", "--no-sleep"]) == 0
    played = json.loads(capsys.readouterr().out)
    assert played["ticks"] == 3
    assert played["mode"] == "speed"
