from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

Pulse = Literal["idle", "fire"]

PRIVILEGED_OBSERVATION_FIELDS = frozenset(
    {
        "agent_xy",
        "target_xy",
        "goal_xy",
        "distance",
        "distance_to_goal",
        "bearing",
        "hp",
        "world_pose",
        "body_yaw",
        "walls",
        "obstacle_contact",
        "goal_visible",
    }
)


@dataclass(frozen=True, slots=True)
class Frame:
    frame_id: int
    timestamp_capture_ns: int
    timestamp_received_ns: int
    width: int
    height: int
    pixel_format: str
    source_id: str
    image: np.ndarray | None = None
    buffer_ref: str | None = None
    clock_id: str = "event"

    def __post_init__(self) -> None:
        if self.image is None and not self.buffer_ref:
            raise ValueError("Frame needs image or buffer_ref")
        if self.image is not None:
            if self.image.ndim != 3 or self.image.shape[2] != 3:
                raise ValueError(f"image must be HWC RGB, got {self.image.shape}")
            if self.image.dtype != np.uint8:
                raise ValueError("image dtype must be uint8")
            if self.image.shape[0] != self.height or self.image.shape[1] != self.width:
                raise ValueError("image shape does not match width/height")
        if self.pixel_format != "rgb8":
            raise ValueError(f"unsupported pixel_format {self.pixel_format!r}")


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    event_id: int
    timestamp_received_ns: int
    event_type: str
    payload: dict[str, Any]
    confidence: float
    source: str
    source_timestamp_ns: int | None = None
    actor_id: int | None = None
    target_id: int | None = None


@dataclass(frozen=True, slots=True)
class EncodedVisual:
    left: float
    center: float
    right: float
    centroid: float | None
    mass: float
    confidence: float


@dataclass(frozen=True, slots=True)
class ValidityMask:
    frame: bool
    visual_features: bool
    target: bool
    motion: bool
    telemetry: bool
    previous_action: bool
    stale: bool
    duplicate: bool = False


@dataclass(frozen=True, slots=True)
class PreviousAction:
    turn: float
    forward: float
    pulses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Observation:
    """Policy observation. No privileged simulator pose."""

    timestamp_ns: int
    frame_id: int
    visual_features: EncodedVisual
    target_bearing: float | None
    target_confidence: float
    motion_estimate: float | None
    motion_confidence: float
    telemetry: tuple[TelemetryEvent, ...]
    validity_mask: ValidityMask
    previous_action: PreviousAction | None
    navigation: object | None = None

    def __post_init__(self) -> None:
        leaked = PRIVILEGED_OBSERVATION_FIELDS.intersection(self.__dataclass_fields__)
        if leaked:
            raise ValueError(f"Observation must not contain {leaked}")


@dataclass(frozen=True, slots=True)
class MotorIntent:
    turn: float
    forward: float
    stop: Pulse
    select_target: Pulse
    attack: Pulse
    confidence: float
    valid_until_ns: int
    strafe: float | None = None

    def clipped(self) -> MotorIntent:
        return MotorIntent(
            turn=float(np.clip(self.turn, -1.0, 1.0)),
            forward=float(np.clip(self.forward, 0.0, 1.0)),
            strafe=None if self.strafe is None else float(np.clip(self.strafe, -1.0, 1.0)),
            stop=self.stop,
            select_target=self.select_target,
            attack=self.attack,
            confidence=float(np.clip(self.confidence, 0.0, 1.0)),
            valid_until_ns=self.valid_until_ns,
        )

    @property
    def pulses(self) -> tuple[str, ...]:
        names: list[str] = []
        if self.stop == "fire":
            names.append("stop")
        if self.select_target == "fire":
            names.append("select_target")
        if self.attack == "fire":
            names.append("attack")
        return tuple(names)


@dataclass(frozen=True, slots=True)
class Command:
    """Decoded, time-bounded command. Pulses are one-shot."""

    turn: float
    forward: float
    strafe: float | None
    pulses: tuple[str, ...]
    issued_at_ns: int
    expires_at_ns: int
    dropped: bool
    drop_reason: str | None = None


@dataclass(frozen=True, slots=True)
class Effect:
    accepted: bool
    reason: str
    mock: bool = True


@dataclass(frozen=True, slots=True)
class StageTimings:
    """Local intervals are mono. Frame age stays on the event clock."""

    wait_frame_ms: float
    frame_age_ms: float | None
    encode_ms: float
    infer_ms: float
    decode_ms: float
    act_ms: float
    wait_effect_ms: float
    interval_clock: str = "mono"
    frame_age_clock: str = "event"
    infer_synced: bool = True
    infer_is_compute: bool = True


@dataclass(frozen=True, slots=True)
class TickRecord:
    tick: int
    observe_ms: float
    infer_ms: float
    decode_ms: float
    act_ms: float
    loop_ms: float
    frame_id: int
    observation: Observation
    intent: MotorIntent
    command: Command
    effect: Effect
    timings: StageTimings | None = None
    reward: float | None = None
    diagnostics: dict[str, Any] | None = None
    frame_ref: str | None = None


@dataclass
class SessionHeader:
    seed: int
    ticks_planned: int
    mock: bool = True
    extras: dict[str, Any] = field(default_factory=dict)
