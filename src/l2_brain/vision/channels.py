from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from l2_brain.contracts import PreviousAction
from l2_brain.vision.flow import FlowField, expansion, mean_flow, residual_objectness

Label = Literal["approach", "camera_turn", "low_confidence", "uncertain"]


@dataclass(frozen=True, slots=True)
class ScaleChannels:
    name: str
    brightness: tuple[float, ...]
    contrast: tuple[float, ...]
    d_pos: tuple[float, ...]
    d_neg: tuple[float, ...]
    flow_u: tuple[float, ...]
    flow_v: tuple[float, ...]
    expansion: float
    motion_confidence: float
    weak_texture_frac: float
    valid_flow_frac: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MotionHypothesis:
    camera_yaw_like: float
    body_forward_like: float
    residual_object_like: float
    command_prior_used: bool
    command_is_not_measurement: bool
    label: Label

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NavigationChannels:
    preprocess_ms: float
    width: int
    height: int
    sectors_x: int
    sectors_y: int
    far: ScaleChannels
    near: ScaleChannels
    target_bearing: float | None
    target_confidence: float
    motion_confidence: float
    expansion: float
    flow_absent_is_not_clear: bool
    duplicate_frame: bool
    abrupt_cut: bool
    lighting_change: float
    hypothesis: MotionHypothesis
    no_object_model: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify(expansion_v: float, mean_u: float, motion_c: float) -> Label:
    """expansion_v is fractional scale (curr vs prev). mean_u is median horizontal flow."""
    if motion_c < 0.16:
        return "low_confidence"
    if expansion_v > 0.03 and abs(mean_u) < 1.6:
        return "approach"
    if abs(mean_u) > 0.95 and expansion_v < 0.025:
        return "camera_turn"
    return "uncertain"


def hypothesis_from_flow(
    field: FlowField,
    *,
    previous: PreviousAction | None,
    expansion_v: float | None = None,
    motion_c: float | None = None,
) -> MotionHypothesis:
    mean_u, mean_v, flow_c = mean_flow(field)
    radial = expansion(field)
    exp = radial if expansion_v is None else expansion_v
    leftover = residual_objectness(field, mean_u, mean_v, radial)
    prior = previous is not None
    camera = abs(mean_u)
    body = max(0.0, exp)
    if prior and previous is not None:
        # Command is a hint only. It never replaces the visual numbers.
        if abs(previous.turn) > 0.25:
            camera = 0.5 * camera + 0.5 * abs(mean_u)
        if previous.forward > 0.25:
            body = 0.5 * body + 0.5 * max(0.0, exp)
    return MotionHypothesis(
        camera_yaw_like=float(camera),
        body_forward_like=float(body),
        residual_object_like=float(leftover),
        command_prior_used=prior,
        command_is_not_measurement=True,
        label=classify(exp, mean_u, flow_c if motion_c is None else motion_c),
    )
