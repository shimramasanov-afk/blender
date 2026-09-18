"""CircuitController over the MaleCNS extract. Isolated from snn_v1 / baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from l2_brain.contracts import MotorIntent, Observation
from l2_brain.control.malecns.loader import Mode, load_subgraph
from l2_brain.control.malecns.network import MaleCNSNetwork, decode_descending, lif_for_graph
from l2_brain.control.snn.controller import encode_observation
from l2_brain.control.snn.types import LIFConfig, PopulationMetrics


@dataclass(frozen=True, slots=True)
class MaleCNSDiagnostics:
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
    mode: str = "bio"


class MaleCNSController:
    """Isolated extract controller. Not a game policy. Not Frozen catalog."""

    def __init__(self, mode: Mode = "bio", *, seed: int = 0, config: LIFConfig | None = None) -> None:
        self.mode: Mode = mode
        self.graph = load_subgraph(mode, seed=seed)
        self.config = config or lif_for_graph(self.graph, seed=seed)
        self._net = MaleCNSNetwork(self.graph, self.config)
        self.name = f"malecns_{mode}"
        self._open = False
        self.last_diag: MaleCNSDiagnostics | None = None
        self.last_metrics: PopulationMetrics | None = None

    def initialize(self) -> None:
        self._open = True
        self.reset_state()

    def reset_state(self) -> None:
        self._net.reset()
        self.last_diag = None
        self.last_metrics = None

    def close(self) -> None:
        self._open = False
        self.reset_state()

    def n_params(self) -> int:
        return int(self._net.w_rec.size + self._net.w_in.size)

    def step(self, observation: Observation, now_ns: int, intent_ttl_ns: int) -> MotorIntent:
        if not self._open:
            raise RuntimeError("MaleCNSController is closed")
        until = now_ns + intent_ttl_ns
        if observation.validity_mask.stale or not observation.validity_mask.frame:
            self.last_metrics = None
            self.last_diag = MaleCNSDiagnostics(
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
                mode=self.mode,
            )
            return _intent(0.0, 0.0, stop=True, confidence=0.0, until=until)
        sensory = encode_observation(observation, self.config)
        traces, metrics = self._net.step_tick(sensory)
        turn, forward = decode_descending(
            traces,
            self.config,
            self._net.dn_left,
            self._net.dn_right,
            self._net.dn_fwd,
            self._net.inhib,
        )
        self.last_metrics = metrics
        self.last_diag = MaleCNSDiagnostics(
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
            mode=self.mode,
        )
        return _intent(
            turn,
            forward,
            stop=False,
            confidence=max(float(observation.target_confidence), 0.15),
            until=until,
        )

    def telemetry(self) -> dict[str, Any]:
        if self.last_metrics is None:
            return {"mode": self.mode, **self.graph.metadata()}
        return {"mode": self.mode, **self.graph.metadata(), **self.last_metrics.to_dict()}


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
