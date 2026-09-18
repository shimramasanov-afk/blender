from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from l2_brain.contracts import PRIVILEGED_OBSERVATION_FIELDS, Frame


@dataclass(frozen=True, slots=True)
class AgentView:
    """The only payload a policy may see from the simulator."""

    frame: Frame
    dropped: bool
    action_delayed: bool

    def __post_init__(self) -> None:
        leaked = PRIVILEGED_OBSERVATION_FIELDS.intersection(self.__dataclass_fields__)
        if leaked:
            raise ValueError(f"AgentView leaked privileged fields: {leaked}")


@dataclass(frozen=True, slots=True)
class GroundTruth:
    """Evaluator-only. Never pass this into a controller."""

    tick: int
    agent_xy: tuple[float, float]
    body_yaw: float
    camera_yaw: float
    goal_xy: tuple[float, float]
    distance_to_goal: float
    obstacle_contact: bool
    goal_visible: bool
    dropped_frame: bool
    action_delayed: bool
    walls: tuple[tuple[float, float, float, float], ...]


@dataclass(frozen=True, slots=True)
class EpisodeResult:
    episode_id: str
    scenario: str
    split: str
    variant: int
    seed: int
    config: dict[str, Any]
    success: bool
    timeout: bool
    collisions: int
    no_progress: bool
    path_length: float
    time_s: float
    direction_changes: int
    ticks: int
    terminal: str
    transfer_claim: bool
    limitation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
