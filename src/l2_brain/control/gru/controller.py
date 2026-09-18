from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from l2_brain.contracts import MotorIntent, Observation
from l2_brain.control.gru.cell import GRUCell
from l2_brain.control.gru.types import GRUConfig
from l2_brain.control.snn.controller import encode_observation
from l2_brain.control.snn.types import LIFConfig


@dataclass(frozen=True, slots=True)
class GRUDiagnostics:
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


class GRUController:
    """Compact GRU on the same 6 sensory channels as snn_core_v1. Not trained."""

    name = "gru_v1"

    def __init__(self, config: GRUConfig | None = None) -> None:
        self.config = config or GRUConfig()
        self._cell = GRUCell(self.config)
        self._sense_cfg = LIFConfig(fov_half_rad=self.config.fov_half_rad)
        self._hidden = np.zeros(self.config.hidden, dtype=np.float64)
        self._open = False
        self.last_diag: GRUDiagnostics | None = None

    def initialize(self) -> None:
        self._open = True
        self.reset_state()

    def reset_state(self) -> None:
        self._hidden = np.zeros(self.config.hidden, dtype=np.float64)
        self.last_diag = None

    def reset_weights(self) -> None:
        self._cell = GRUCell(self.config)

    def close(self) -> None:
        self._open = False
        self.reset_state()

    @property
    def hidden(self) -> np.ndarray:
        return self._hidden.copy()

    def n_params(self) -> int:
        return self._cell.n_params()

    def step(self, observation: Observation, now_ns: int, intent_ttl_ns: int) -> MotorIntent:
        if not self._open:
            raise RuntimeError("GRUController is closed")
        until = now_ns + intent_ttl_ns
        if observation.validity_mask.stale or not observation.validity_mask.frame:
            self.last_diag = GRUDiagnostics(
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
        sensory = encode_observation(observation, self._sense_cfg)
        prev = self._hidden if self.config.with_memory else np.zeros(self.config.hidden, dtype=np.float64)
        nxt = self._cell.step(sensory, prev)
        self._hidden = nxt if self.config.with_memory else np.zeros(self.config.hidden, dtype=np.float64)
        residual = self._cell.readout(nxt)
        turn_b, forward_b = _braitenberg(sensory, self.config)
        turn = float(np.clip(turn_b + residual[0], -1.0, 1.0))
        forward = float(np.clip(forward_b + residual[1], 0.0, 1.0))
        self.last_diag = GRUDiagnostics(
            attract_turn=turn_b,
            avoid_turn=0.0,
            memory_turn=float(residual[0]),
            risk=float(sensory[3]),
            progress=0.0,
            side=1.0 if turn > 0.0 else (-1.0 if turn < 0.0 else 0.0),
            side_age=0,
            turn=turn,
            forward=forward,
            stop=False,
            reason="seek",
            target_confidence=float(observation.target_confidence),
        )
        return _intent(turn, forward, stop=False, confidence=max(float(observation.target_confidence), 0.15), until=until)


def _braitenberg(sensory: np.ndarray, cfg: GRUConfig) -> tuple[float, float]:
    left, right, conf, risk, _mass, align = (float(v) for v in sensory)
    turn = cfg.k_turn * (right - left)
    acquired = conf >= 0.12
    cruise = cfg.k_forward if acquired else 0.0
    forward = cruise * max(align, 0.25 if acquired else 0.0) * (1.0 - 0.25 * risk)
    return float(np.clip(turn, -cfg.k_turn, cfg.k_turn)), float(np.clip(forward, 0.0, 1.0))


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
