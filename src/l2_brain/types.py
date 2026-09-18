from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Observation:
    """Official controller input. No privileged world state."""

    frame: np.ndarray
    timestamp_ns: int
    tick: int

    def __post_init__(self) -> None:
        frame = self.frame
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(f"frame must be HWC RGB, got {frame.shape}")
        if frame.dtype != np.uint8:
            raise ValueError(f"frame dtype must be uint8, got {frame.dtype}")


@dataclass(frozen=True, slots=True)
class Action:
    turn: float
    forward: float
    engage: float

    def clipped(self) -> Action:
        return Action(
            turn=float(np.clip(self.turn, -1.0, 1.0)),
            forward=float(np.clip(self.forward, 0.0, 1.0)),
            engage=float(np.clip(self.engage, 0.0, 1.0)),
        )


@dataclass(frozen=True, slots=True)
class TickMetrics:
    observe_ms: float
    infer_ms: float
    act_ms: float
    loop_ms: float


@dataclass(frozen=True, slots=True)
class StepInfo:
    agent_xy: tuple[float, float]
    target_xy: tuple[float, float] | None
    distance: float
    bearing: float
    blocked: bool
    success: bool
    stuck: bool
    truncated: bool
    stuck_reason: str | None = None


@dataclass(frozen=True, slots=True)
class EpisodeReport:
    controller: str
    scenario: str
    seed: int
    success: bool
    stuck: bool
    truncated: bool
    ticks: int
    stuck_reason: str | None
    infer_ms: tuple[float, ...]
    loop_ms: tuple[float, ...]
    observe_ms: tuple[float, ...]
    act_ms: tuple[float, ...]

    @property
    def mean_infer_ms(self) -> float:
        return float(np.mean(self.infer_ms)) if self.infer_ms else 0.0

    @property
    def mean_loop_ms(self) -> float:
        return float(np.mean(self.loop_ms)) if self.loop_ms else 0.0
