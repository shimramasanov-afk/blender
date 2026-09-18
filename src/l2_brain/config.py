from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StandConfig:
    tick_hz: int = 20
    max_steps: int = 200
    frame_h: int = 64
    frame_w: int = 64
    fov_rad: float = 1.2
    max_turn: float = 0.18
    max_speed: float = 0.12
    engage_distance: float = 2.0
    engage_angle: float = 0.22
    world: float = 16.0
    agent_radius: float = 0.28
    target_radius: float = 0.48
    frozen_window: int = 25
    frozen_xy: float = 0.08
    frozen_yaw: float = 0.05
    progress_window: int = 40
    progress_eps: float = 0.10
    blocked_frac: float = 0.50

    @property
    def dt(self) -> float:
        return 1.0 / self.tick_hz


SCENARIOS = ("open_field", "pursuit", "occluded", "memory_probe")
CONTROLLERS = ("reactive", "recurrent", "snn")
