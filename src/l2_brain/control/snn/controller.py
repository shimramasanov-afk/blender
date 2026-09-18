from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from l2_brain.contracts import MotorIntent, Observation
from l2_brain.control.snn.network import SpikingNetwork
from l2_brain.control.snn.plasticity import RewardModulatedSTDP
from l2_brain.control.snn.readout import decode_motor
from l2_brain.control.snn.types import LIFConfig, PopulationMetrics


@dataclass(frozen=True, slots=True)
class SNNDiagnostics:
    attract_turn: float
    avoid_turn: float
    memory_turn: float
    risk: float
    progress: float
    side: float
    side_age: int
    turn: float
    forward: float
    stop: bool
    reason: str
    target_confidence: float
    situation: str = "move"
    progress_conf: float = 0.0
    no_progress_evidence: float = 0.0
    recovering: bool = False
    recover_age: int = 0
    scene_repeat_score: float = 0.0
    command_is_not_measurement: bool = True
    firing_rate_hz: float = 0.0
    silent_ratio: float = 1.0
    saturated_ratio: float = 0.0
    v_min: float = 0.0
    v_mean: float = 0.0
    v_max: float = 0.0


def encode_observation(observation: Observation, cfg: LIFConfig) -> np.ndarray:
    """left, right, conf, risk, mass, align. No privileged pose."""
    conf = float(observation.target_confidence)
    raw = observation.target_bearing
    valid = observation.validity_mask.target and raw is not None
    if not valid or raw is None:
        bearing = 0.0
        conf = 0.0
    else:
        bearing = float(np.clip(raw / cfg.fov_half_rad, -1.0, 1.0))
    nav = observation.navigation
    risk = 0.0
    if nav is not None:
        risk = max(0.0, float(getattr(nav, "expansion", 0.0)))
    mass = float(observation.visual_features.mass)
    align = max(0.0, 1.0 - abs(bearing)) * conf
    return np.array(
        [max(0.0, -bearing) * conf, max(0.0, bearing) * conf, conf, risk, mass, align],
        dtype=np.float64,
    )


class SNNController:
    """Isolated L1 sandbox. CircuitController. Not baseline. Not MaleCNS."""

    name = "snn_core_v1"

    def __init__(self, config: LIFConfig | None = None) -> None:
        self._template = config or LIFConfig()
        self.config = self._template
        self._net = SpikingNetwork(self.config)
        self._plasticity: RewardModulatedSTDP | None = None
        self._open = False
        self.last_diag: SNNDiagnostics | None = None
        self.last_metrics: PopulationMetrics | None = None

    def initialize(self) -> None:
        self._open = True
        self.reset_state()

    def reset_state(self) -> None:
        self._net.reset()
        if self._plasticity is not None:
            self._plasticity.reset_traces()
        self.last_diag = None
        self.last_metrics = None

    def reset_weights(self) -> None:
        self.config = self._template
        self._net = SpikingNetwork(self.config)

    def close(self) -> None:
        self._open = False
        self.reset_state()

    def n_params(self) -> int:
        return int(self._net.w_rec.size + self._net.w_in.size)

    def attach_plasticity(self, plasticity: RewardModulatedSTDP | None) -> None:
        self._plasticity = plasticity

    def apply_trainer_signal(self, reward: float) -> None:
        """Privileged critic. Not a sensory feature and not part of Observation."""
        if self._plasticity is None:
            return
        self._net.w_in = self._plasticity.modulate(self._net.w_in, reward)

    def step(self, observation: Observation, now_ns: int, intent_ttl_ns: int) -> MotorIntent:
        if not self._open:
            raise RuntimeError("SNNController is closed")
        until = now_ns + intent_ttl_ns
        if observation.validity_mask.stale or not observation.validity_mask.frame:
            self.last_metrics = None
            self.last_diag = SNNDiagnostics(
                attract_turn=0.0,
                avoid_turn=0.0,
                memory_turn=0.0,
                risk=0.0,
                progress=0.0,
                side=0.0,
                side_age=0,
                turn=0.0,
                forward=0.0,
                stop=True,
                reason="stale",
                target_confidence=0.0,
                situation="unreliable",
            )
            return _intent(0.0, 0.0, stop=True, confidence=0.0, until=until)
        sensory = encode_observation(observation, self.config)
        traces, metrics = self._net.step_tick(sensory, self._plasticity)
        turn, forward = decode_motor(traces, self.config, self._net.pools)
        self.last_metrics = metrics
        self.last_diag = SNNDiagnostics(
            attract_turn=turn,
            avoid_turn=0.0,
            memory_turn=0.0,
            risk=sensory[3],
            progress=0.0,
            side=1.0 if turn > 0.0 else (-1.0 if turn < 0.0 else 0.0),
            side_age=0,
            turn=turn,
            forward=forward,
            stop=False,
            reason="seek",
            target_confidence=float(observation.target_confidence),
            firing_rate_hz=metrics.firing_rate_hz,
            silent_ratio=metrics.silent_ratio,
            saturated_ratio=metrics.saturated_ratio,
            v_min=metrics.v_min,
            v_mean=metrics.v_mean,
            v_max=metrics.v_max,
        )
        return _intent(turn, forward, stop=False, confidence=max(float(observation.target_confidence), 0.15), until=until)

    def telemetry(self) -> dict[str, Any]:
        if self.last_metrics is None:
            return {}
        return self.last_metrics.to_dict()


def _intent(turn: float, forward: float, *, stop: bool, confidence: float, until: int) -> MotorIntent:
    return MotorIntent(
        turn=turn,
        forward=0.0 if stop else forward,
        strafe=None,
        stop="fire" if stop else "idle",
        select_target="idle",
        attack="idle",
        confidence=confidence,
        valid_until_ns=until,
    ).clipped()
