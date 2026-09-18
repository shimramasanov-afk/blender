from __future__ import annotations

import logging
import random

import numpy as np

from l2_brain.circuit.config import CircuitConfig
from l2_brain.factory import build_encoder
from l2_brain.circuit.mock_io import MockFrameSource, MockInputBackend, MockTelemetrySource
from l2_brain.circuit.persist import CircuitEvaluator
from l2_brain.circuit.policy import FeatureController, PulseDecoder, attach_previous
from l2_brain.circuit.protocols import (
    ActionDecoder,
    CircuitController,
    Evaluator,
    FrameSource,
    InputBackend,
    Recorder,
    TelemetrySource,
    VisualEncoder,
)
from l2_brain.contracts import Observation, SessionHeader, StageTimings, TickRecord
from l2_brain.experiment.clocks import event_ns, mono_ns, stamp
from l2_brain.experiment.identity import OFFLINE_REPLAY_LIMIT, code_identity, public_circuit_config
from l2_brain.experiment.store import build_recorder
from l2_brain.experiment.timing import measure_compute
from l2_brain.logging_setup import setup_logging

log = logging.getLogger("l2_brain.circuit")


class Circuit:
    def __init__(
        self,
        config: CircuitConfig,
        frames: FrameSource,
        telemetry: TelemetrySource,
        encoder: VisualEncoder,
        controller: CircuitController,
        decoder: ActionDecoder,
        backend: InputBackend,
        recorder: Recorder,
        evaluator: Evaluator,
    ) -> None:
        self.config = config
        self.frames = frames
        self.telemetry = telemetry
        self.encoder = encoder
        self.controller = controller
        self.decoder = decoder
        self.backend = backend
        self.recorder = recorder
        self.evaluator = evaluator
        self._open = False
        self._tick = 0
        self._last_obs: Observation | None = None

    def initialize(self) -> None:
        setup_logging(self.config.log_level)
        random.seed(self.config.seed)
        np.random.seed(self.config.seed)
        self.frames.initialize()
        self.telemetry.initialize()
        self.encoder.initialize()
        self.controller.initialize()
        self.decoder.initialize()
        self.backend.initialize()
        header = SessionHeader(
            seed=self.config.seed,
            ticks_planned=self.config.ticks,
            mock=True,
            extras={
                "controller": self.controller.name,
                "source": self.config.source_id,
                "code": code_identity(),
                "model_version": self.config.model_version,
                "config": public_circuit_config(self.config),
                "offline_replay_limitation": OFFLINE_REPLAY_LIMIT,
            },
        )
        initialize = getattr(self.recorder, "initialize")
        try:
            initialize(header)
        except TypeError:
            initialize()
        self.evaluator.initialize()
        self._open = True
        self._tick = 0
        self._last_obs = None
        log.info(
            "circuit open",
            extra={"event": "circuit.initialize", "mock": True, "tick": 0},
        )

    def reset_episode(self, seed: int | None = None) -> None:
        use = self.config.seed if seed is None else seed
        random.seed(use)
        np.random.seed(use)
        self.frames.reset_episode(use)
        self.telemetry.reset_episode(use)
        self.encoder.reset_episode(use)
        self.controller.reset_state()
        self.backend.reset_episode(use)
        self._tick = 0
        self._last_obs = None
        log.info("episode reset", extra={"event": "circuit.reset_episode", "mock": True, "tick": 0})

    def reset_weights(self) -> None:
        self.controller.reset_weights()
        log.info("weights reset", extra={"event": "circuit.reset_weights", "mock": True})

    def step(self) -> TickRecord:
        if not self._open:
            raise RuntimeError("Circuit is closed")
        loop_start = stamp(mono_ns(), "mono")
        wait_start = mono_ns()
        frame = self.frames.latest()
        wait_frame_ms = (mono_ns() - wait_start) / 1_000_000.0
        now = self._now()
        frame_age_ms = self._frame_age_ms(frame, now)
        stale = frame_age_ms is not None and (frame_age_ms * 1_000_000.0) > self.config.stale_frame_ns
        if stale:
            log.warning(
                "stale frame",
                extra={"event": "circuit.stale", "mock": True, "tick": self._tick, "frame_id": frame.frame_id, "reason": "stale_frame"},
            )
        encode_start = mono_ns()
        events = self.telemetry.poll()
        observation = self.encoder.encode(frame, events, self._last_obs, now, stale)
        encode_ms = (mono_ns() - encode_start) / 1_000_000.0
        measured = measure_compute(
            lambda: self.controller.step(observation, now, self.config.max_intent_age_ns),
            require_gpu_sync=self.config.gpu_sync,
        )
        intent = measured.value
        infer_ms = measured.elapsed_ms
        decode_start = mono_ns()
        command = self.decoder.decode(intent, now)
        decode_ms = (mono_ns() - decode_start) / 1_000_000.0
        if command.dropped:
            log.warning(
                "intent dropped",
                extra={
                    "event": "circuit.fallback",
                    "mock": True,
                    "tick": self._tick,
                    "dropped": True,
                    "reason": command.drop_reason,
                },
            )
        act_start = mono_ns()
        effect = self.backend.apply(command)
        act_ms = (mono_ns() - act_start) / 1_000_000.0
        effect_start = mono_ns()
        wait_effect = getattr(self.backend, "wait_observed_effect", None)
        if wait_effect is not None:
            effect = wait_effect(effect)
        wait_effect_ms = (mono_ns() - effect_start) / 1_000_000.0
        loop_ms = (mono_ns() - loop_start.value_ns) / 1_000_000.0
        observe_ms = wait_frame_ms + encode_ms
        store_frame = getattr(self.recorder, "store_frame", None)
        frame_ref = store_frame(self._tick, frame.image) if store_frame is not None else None
        writer_drops = int(getattr(self.recorder, "writer_drops", 0))
        frame_drops = int(getattr(self.frames, "queue_drops", 0))
        stored = attach_previous(observation, command)
        timings = StageTimings(
            wait_frame_ms=wait_frame_ms,
            frame_age_ms=frame_age_ms,
            encode_ms=encode_ms,
            infer_ms=infer_ms,
            decode_ms=decode_ms,
            act_ms=act_ms,
            wait_effect_ms=wait_effect_ms,
            infer_synced=measured.synced,
            infer_is_compute=measured.is_compute,
        )
        diagnostics = {
            "stale": stale,
            "command_dropped": command.dropped,
            "effect_accepted": effect.accepted,
            "frame_queue_drops": frame_drops,
            "writer_drops": writer_drops,
            "encoder_confidence": stored.visual_features.confidence,
            "infer_reason": measured.reason,
        }
        record = TickRecord(
            tick=self._tick,
            observe_ms=observe_ms,
            infer_ms=infer_ms,
            decode_ms=decode_ms,
            act_ms=act_ms,
            loop_ms=loop_ms,
            frame_id=frame.frame_id,
            observation=stored,
            intent=intent,
            command=command,
            effect=effect,
            timings=timings,
            reward=None,
            diagnostics=diagnostics,
            frame_ref=frame_ref,
        )
        self.recorder.write(record)
        self.evaluator.observe(record)
        self._last_obs = stored
        self._tick += 1
        log.info(
            "tick",
            extra={"event": "circuit.tick", "mock": True, "tick": record.tick, "frame_id": frame.frame_id},
        )
        return record

    def run(self, ticks: int | None = None) -> list[TickRecord]:
        n = self.config.ticks if ticks is None else ticks
        records: list[TickRecord] = []
        try:
            if not self._open:
                self.initialize()
            self.reset_episode(self.config.seed)
            for _ in range(n):
                records.append(self.step())
        finally:
            self.close()
        return records

    def close(self) -> None:
        if not self._open:
            return
        self.backend.emergency_stop()
        self.backend.close()
        self.controller.close()
        self.decoder.close()
        self.encoder.close()
        self.telemetry.close()
        self.frames.close()
        self.recorder.close()
        self.evaluator.close()
        self._open = False
        log.info("circuit closed", extra={"event": "circuit.close", "mock": True})

    def _now(self) -> int:
        if self.config.now_ns is not None:
            return int(self.config.now_ns())
        return event_ns()

    def _frame_age_ms(self, frame, now: int) -> float | None:
        if getattr(frame, "clock_id", "event") != "event":
            return None
        return (now - frame.timestamp_received_ns) / 1_000_000.0


def build_mock_circuit(config: CircuitConfig) -> Circuit:
    return Circuit(
        config=config,
        frames=MockFrameSource(config),
        telemetry=MockTelemetrySource(),
        encoder=build_encoder(config.encoder_name),
        controller=FeatureController(),
        decoder=PulseDecoder(strafe_supported=config.strafe_supported),
        backend=MockInputBackend(),
        recorder=build_recorder(config),
        evaluator=CircuitEvaluator(),
    )
