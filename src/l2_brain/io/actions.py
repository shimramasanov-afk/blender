from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class MouseButton(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class TargetMethod(StrEnum):
    NEXT_HOTKEY = "next_hotkey"
    SILHOUETTE_CLICK = "silhouette_click"


@dataclass(frozen=True, slots=True)
class CameraRotate:
    dx_pixels: int
    dy_pixels: int


@dataclass(frozen=True, slots=True)
class GroundClick:
    x: int
    y: int
    button: MouseButton = MouseButton.LEFT


@dataclass(frozen=True, slots=True)
class TargetSelect:
    method: TargetMethod
    coords: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class SkillActivate:
    slot: int
    key: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class HoldKey:
    key: str
    duration_ms: int = 0
    state: str = "down"


@dataclass(frozen=True, slots=True)
class EmergencyStop:
    reason: str = "operator"


@dataclass(frozen=True, slots=True)
class Pickup:
    """Synthetic loot pickup. Dry-run only; not a live client packet."""

    entity_id: int


GameAction = CameraRotate | GroundClick | TargetSelect | SkillActivate | HoldKey | EmergencyStop | Pickup


@dataclass(frozen=True, slots=True)
class InputEvent:
    """Dry-run log row. hid_sent is always false in hod28."""

    timestamp_ns: int
    action_type: str
    key: str | None
    button: str | None
    hold_duration_ms: int | None
    target_window: str
    dx: int | None
    dy: int | None
    x: int | None
    y: int | None
    accepted: bool
    reason: str
    dry_run: bool = True
    hid_sent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
