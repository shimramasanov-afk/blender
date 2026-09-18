"""Privileged trainer reward. Never a sensory channel. Never written into Observation."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

from l2_brain.sim.views import GroundTruth


@dataclass(frozen=True, slots=True)
class RewardConfig:
    goal: float = 1.0
    progress: float = 0.02
    collision: float = -0.10
    stall: float = -0.01
    progress_quantum: float = 0.08
    stall_eps: float = 0.02
    stall_ticks: int = 8
    delay_ticks: int = 2
    normalize: bool = True
    ema: float = 0.05
    clip: float = 1.0

    def __post_init__(self) -> None:
        if self.progress_quantum <= 0.0 or self.stall_eps < 0.0:
            raise ValueError("progress_quantum must be > 0 and stall_eps >= 0")
        if self.stall_ticks < 1 or self.delay_ticks < 0:
            raise ValueError("stall_ticks must be >= 1 and delay_ticks >= 0")
        if not 0.0 < self.ema <= 1.0 or self.clip <= 0.0:
            raise ValueError("ema must be in (0, 1] and clip > 0")


@dataclass(frozen=True, slots=True)
class RewardSample:
    """Trainer telemetry. Privileged. Not Observation."""

    raw: float
    delayed: float
    delivered: float
    privileged: bool = True
    goal: bool = False
    collision: bool = False
    progress_quanta: int = 0
    stalled: bool = False


class RewardEngine:
    """Scalar critic from GroundTruth. Distance never enters the policy vector."""

    source = "privileged_ground_truth"

    def __init__(self, config: RewardConfig | None = None) -> None:
        self.config = config or RewardConfig()
        self._delay = deque(0.0 for _ in range(self.config.delay_ticks))
        self._stall_age = 0
        self._mean = 0.0
        self._var = 1.0
        self._seen = 0

    def reset(self) -> None:
        self._delay = deque(0.0 for _ in range(self.config.delay_ticks))
        self._stall_age = 0

    def step(self, previous: GroundTruth, current: GroundTruth, *, success: bool) -> RewardSample:
        cfg = self.config
        raw = 0.0
        delta = float(previous.distance_to_goal - current.distance_to_goal)
        quanta = int(delta // cfg.progress_quantum) if delta >= cfg.progress_quantum else 0
        if quanta:
            raw += cfg.progress * quanta
            self._stall_age = 0
        elif abs(delta) < cfg.stall_eps:
            self._stall_age += 1
        else:
            self._stall_age = 0
        stalled = self._stall_age >= cfg.stall_ticks
        if stalled:
            raw += cfg.stall
        collision = bool(current.obstacle_contact and not previous.obstacle_contact)
        if collision:
            raw += cfg.collision
        if success:
            raw += cfg.goal
        if cfg.delay_ticks == 0:
            delayed = raw
        else:
            self._delay.append(raw)
            delayed = float(self._delay.popleft())
        delivered = self._normalize(delayed) if cfg.normalize else delayed
        return RewardSample(
            raw=raw,
            delayed=delayed,
            delivered=float(delivered),
            goal=success,
            collision=collision,
            progress_quanta=quanta,
            stalled=stalled,
        )

    def _normalize(self, value: float) -> float:
        cfg = self.config
        self._seen += 1
        delta = value - self._mean
        self._mean += cfg.ema * delta
        self._var = (1.0 - cfg.ema) * self._var + cfg.ema * delta * delta
        scale = max(self._var, 1e-6) ** 0.5
        # Warm-up: first ticks keep magnitude instead of exploding z-score.
        if self._seen < 8:
            return float(max(-cfg.clip, min(cfg.clip, value)))
        return float(max(-cfg.clip, min(cfg.clip, (value - self._mean) / scale)))

    def to_dict(self) -> dict[str, Any]:
        return {"config": asdict(self.config), "source": self.source, "privileged": True}
