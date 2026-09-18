from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Split = Literal["training", "validation", "held_out"]

FROZEN_SCENARIO_IDS = (
    "open_goal",
    "single_obstacle",
    "narrow_gate",
    "corridor",
    "long_fence",
    "u_trap",
    "dead_end",
    "weak_texture",
    "moving_target",
    "vanishing_target",
    "camera_spin",
    "latency_drops",
)
SCENARIO_ALIASES = {
    "rear_goal_u": "u_trap",
    "rear_goal_corridor": "dead_end",
}
INTEGRITY_SCENARIO_IDS = (
    "open_goal",
    "single_obstacle",
    "narrow_gate",
    "corridor",
    "long_fence",
    "rear_goal_u",
    "rear_goal_corridor",
    "weak_texture",
    "moving_target",
    "vanishing_target",
    "camera_spin",
    "latency_drops",
    "detour_visible",
    "side_hold_jog",
    "loop_yard",
)
DIAGNOSTIC_SCENARIO_IDS = ("push_wall",)
SCENARIO_IDS = tuple(dict.fromkeys(FROZEN_SCENARIO_IDS + INTEGRITY_SCENARIO_IDS + DIAGNOSTIC_SCENARIO_IDS))
SUITE_IDS = {
    "frozen": FROZEN_SCENARIO_IDS,
    "integrity": INTEGRITY_SCENARIO_IDS,
    "diagnostic": DIAGNOSTIC_SCENARIO_IDS,
}

SPLIT_VARIANTS: dict[Split, tuple[int, ...]] = {
    "training": (0, 1, 2),
    "validation": (3,),
    "held_out": (4,),
}


@dataclass(frozen=True, slots=True)
class SimConfig:
    frame_w: int = 64
    frame_h: int = 64
    fov_h: float = 1.2
    fov_v: float = 0.9
    camera_height: float = 0.55
    camera_pitch: float = -0.12
    max_speed: float = 0.12
    max_turn: float = 0.18
    action_delay_ticks: int = 0
    drop_ticks: tuple[int, ...] = ()
    lighting: float = 1.0
    texture_strength: float = 1.0
    tick_hz: int = 20
    max_steps: int = 200
    agent_radius: float = 0.28
    goal_radius: float = 0.75
    world: float = 16.0
    wall_height: float = 1.6
    goal_height: float = 1.1
    source_id: str = "sim.perspective"
    start_xy: tuple[float, float] | None = None
    start_yaw: float | None = None
    goal_xy: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if self.frame_w < 8 or self.frame_h < 8:
            raise ValueError("frame size must be >= 8")
        if self.tick_hz < 1 or self.max_steps < 1:
            raise ValueError("tick_hz and max_steps must be >= 1")
        if self.action_delay_ticks < 0:
            raise ValueError("action_delay_ticks must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["drop_ticks"] = list(self.drop_ticks)
        return data


@dataclass(frozen=True, slots=True)
class EpisodeSpec:
    scenario: str
    split: Split
    variant: int
    seed: int
    config: SimConfig = field(default_factory=SimConfig)

    def __post_init__(self) -> None:
        if self.scenario not in SCENARIO_IDS:
            raise ValueError(f"unknown scenario {self.scenario!r}")
        if self.variant not in SPLIT_VARIANTS[self.split]:
            raise ValueError(f"variant {self.variant} not in split {self.split}")

    @property
    def episode_id(self) -> str:
        return f"{self.scenario}:{self.split}:v{self.variant}:s{self.seed}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "scenario": self.scenario,
            "split": self.split,
            "variant": self.variant,
            "seed": self.seed,
            "config": self.config.to_dict(),
        }


def catalog(seed: int, *, config: SimConfig | None = None, suite: str = "frozen") -> list[EpisodeSpec]:
    if suite not in SUITE_IDS:
        raise ValueError(f"unknown suite {suite!r}")
    cfg = config or SimConfig()
    specs: list[EpisodeSpec] = []
    for scenario in SUITE_IDS[suite]:
        for split, variants in SPLIT_VARIANTS.items():
            for variant in variants:
                specs.append(
                    EpisodeSpec(
                        scenario=scenario,
                        split=split,
                        variant=variant,
                        seed=seed,
                        config=cfg,
                    )
                )
    return specs
