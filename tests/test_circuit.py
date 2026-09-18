from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from l2_brain.circuit.config import CircuitConfig
from l2_brain.circuit.loop import build_mock_circuit
from l2_brain.circuit.persist import intent_from_json, read_session
from l2_brain.circuit.policy import FeatureController, PulseDecoder
from l2_brain.circuit.replay import replay_recorded_observations
from l2_brain.cli import main
from l2_brain.contracts import PRIVILEGED_OBSERVATION_FIELDS, Frame, MotorIntent
from l2_brain.types import Observation as StandObservation


def test_mock_circuit_full_cycle(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    config = CircuitConfig(seed=0, ticks=12, record_path=path, log_level="WARNING")
    records = build_mock_circuit(config).run()
    assert len(records) == 12
    assert all(r.effect.mock for r in records)
    assert all(r.intent.valid_until_ns > 0 for r in records)
    assert any(abs(r.intent.turn) > 0 or r.intent.forward > 0 or r.intent.pulses for r in records)
    header, ticks = read_session(path)
    assert header is not None
    assert header.mock
    assert len(ticks) == 12


def test_observation_has_no_privileged_fields() -> None:
    records = build_mock_circuit(CircuitConfig(ticks=1, log_level="ERROR")).run()
    obs = records[0].observation
    assert PRIVILEGED_OBSERVATION_FIELDS.isdisjoint(obs.__dataclass_fields__)
    assert not hasattr(obs, "agent_xy")
    assert not hasattr(obs, "target_xy")


def test_stand_observation_still_frame_only() -> None:
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    stand = StandObservation(frame=frame, timestamp_ns=1, tick=0)
    assert stand.tick == 0


def test_expired_intent_is_dropped() -> None:
    decoder = PulseDecoder()
    decoder.initialize()
    command = decoder.decode(
        MotorIntent(
            turn=1.0,
            forward=1.0,
            stop="idle",
            select_target="idle",
            attack="fire",
            confidence=1.0,
            valid_until_ns=10,
        ),
        now_ns=11,
    )
    decoder.close()
    assert command.dropped
    assert command.drop_reason == "intent_expired"
    assert command.turn == 0.0
    assert "stop" in command.pulses


def test_reset_state_does_not_reset_weights() -> None:
    ctl = FeatureController()
    ctl.initialize()
    ctl._gain = 9.0
    ctl._side = -1.0
    ctl.reset_state()
    assert ctl._gain == 9.0
    assert ctl._side == 0.0
    ctl.reset_weights()
    assert ctl._gain == ctl._default_gain
    ctl.close()


def test_stale_frame_stops_motion() -> None:
    clock = {"t": 1_000_000_000}

    def now() -> int:
        return clock["t"]

    config = CircuitConfig(ticks=1, now_ns=now, stale_frame_ns=1_000, log_level="ERROR")
    circuit = build_mock_circuit(config)
    circuit.initialize()
    circuit.reset_episode(0)
    image = np.zeros((config.frame_h, config.frame_w, 3), dtype=np.uint8)
    image[20:40, 10:20] = (220, 36, 36)
    circuit.frames.inject(
        Frame(
            frame_id=99,
            timestamp_capture_ns=clock["t"] - 50_000,
            timestamp_received_ns=clock["t"] - 10_000,
            width=config.frame_w,
            height=config.frame_h,
            pixel_format="rgb8",
            source_id="mock.blob",
            image=image,
        )
    )
    record = circuit.step()
    circuit.close()
    assert record.observation.validity_mask.stale
    assert record.intent.stop == "fire"
    assert record.intent.forward == 0.0


def test_pulses_are_not_held() -> None:
    config = CircuitConfig(ticks=8, log_level="ERROR")
    circuit = build_mock_circuit(config)
    circuit.initialize()
    circuit.reset_episode(0)
    for _ in range(8):
        circuit.step()
        assert circuit.backend.held == ()
    circuit.close()


def test_close_is_idempotent() -> None:
    circuit = build_mock_circuit(CircuitConfig(ticks=2, log_level="ERROR"))
    circuit.run()
    circuit.close()
    circuit.close()


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        CircuitConfig(ticks=0)


def test_record_and_replay_match(tmp_path: Path) -> None:
    path = tmp_path / "rec.jsonl"
    config = CircuitConfig(seed=3, ticks=6, record_path=path, log_level="ERROR")
    recorded = build_mock_circuit(config).run()
    replayed = replay_recorded_observations(path, now_ns=10**15)
    assert len(replayed) == 6
    for rec, (intent, _cmd) in zip(recorded, replayed, strict=True):
        stored = intent_from_json(
            json.loads(path.read_text(encoding="utf-8").splitlines()[rec.tick + 1])["intent"]
        )
        assert abs(intent.turn - stored.turn) < 1e-6
        assert intent.attack == stored.attack


def test_cli_mock_and_doctor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "cli.jsonl"
    assert main(["mock", "--ticks", "4", "--seed", "1", "--record", str(out), "--log-level", "ERROR"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["ticks"] == 4
    assert printed["mock"] is True
    assert out.is_file()
    assert main(["doctor"]) == 0
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["accel"] == "numpy_cpu"
    assert doctor["game_client"] == "not_connected"
    assert main(["replay", str(out)]) == 0
    replayed = json.loads(capsys.readouterr().out)
    assert replayed["offline_replay"] is True
    assert replayed["closed_loop"] is False
    assert replayed["ticks"] == 4
