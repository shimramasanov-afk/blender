from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Union

TelemetrySourceName = Literal["sim_ground_truth", "ui_vision", "mock"]


@dataclass(frozen=True, slots=True)
class HealthUpdate:
    timestamp_ns: int
    source: TelemetrySourceName
    confidence: float
    current_hp: float
    max_hp: float
    delta: float
    is_self: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TargetState:
    timestamp_ns: int
    source: TelemetrySourceName
    confidence: float
    locked: bool
    target_id: int | None
    hp_percent: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CombatAction:
    timestamp_ns: int
    source: TelemetrySourceName
    confidence: float
    action_type: str
    confirmed: bool
    damage: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EntityDefeated:
    timestamp_ns: int
    source: TelemetrySourceName
    confidence: float
    entity_id: int
    is_target: bool
    xp_gained: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RangeCue:
    """Privileged sim range. Not an Observation field."""

    timestamp_ns: int
    source: TelemetrySourceName
    confidence: float
    distance_m: float
    in_range: bool
    privileged: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LootSpawned:
    timestamp_ns: int
    source: TelemetrySourceName
    confidence: float
    x: float
    y: float
    entity_id: int
    privileged: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LootCollected:
    timestamp_ns: int
    source: TelemetrySourceName
    confidence: float
    entity_id: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CycleCompleted:
    timestamp_ns: int
    source: TelemetrySourceName
    confidence: float
    kills_count: int
    loot_count: int
    total_ticks: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CombatEvent = Union[
    HealthUpdate,
    TargetState,
    CombatAction,
    EntityDefeated,
    RangeCue,
    LootSpawned,
    LootCollected,
    CycleCompleted,
]
