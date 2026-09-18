from __future__ import annotations

from l2_brain.circuit.loop import Circuit
from l2_brain.factory import build_encoder
from l2_brain.circuit.mock_io import MockInputBackend, MockTelemetrySource
from l2_brain.circuit.persist import CircuitEvaluator
from l2_brain.circuit.policy import FeatureController, PulseDecoder
from l2_brain.circuit.config import CircuitConfig
from l2_brain.experiment.store import build_recorder
from l2_brain.capture.sck import SCKFrameSource


def build_sck_circuit(config: CircuitConfig, frames: SCKFrameSource) -> Circuit:
    return Circuit(
        config=config,
        frames=frames,
        telemetry=MockTelemetrySource(),
        encoder=build_encoder(config.encoder_name),
        controller=FeatureController(),
        decoder=PulseDecoder(strafe_supported=config.strafe_supported),
        backend=MockInputBackend(),
        recorder=build_recorder(config),
        evaluator=CircuitEvaluator(),
    )
