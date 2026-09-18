from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

MoveMode = Literal["hold_forward", "ground_click"]


@dataclass(frozen=True, slots=True)
class GameInputProfile:
    """Template bindings. Not a measured L2 client map. Q1/Q3/Q5 stay unknown."""

    name: str = "mmorpg_template_v0"
    target_window: str = "unknown-game-window"
    press_duration_ms: int = 40
    key_repeat_cooldown_ms: int = 80
    yaw_to_dx_pixels: float = 80.0
    yaw_deadzone: float = 0.05
    move_mode: MoveMode = "hold_forward"
    move_forward_key: str = "w"
    ground_click_xy: tuple[int, int] = (640, 520)
    next_target_key: str = "F1"
    attack_key: str = "F2"
    skill_keys: tuple[str, ...] = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=")
    kill_switch: str = "F12"
    watchdog_timeout_ms: int = 250

    def __post_init__(self) -> None:
        if self.press_duration_ms < 1 or self.key_repeat_cooldown_ms < 0:
            raise ValueError("press_duration_ms must be >= 1 and cooldown >= 0")
        if self.yaw_to_dx_pixels <= 0.0 or self.yaw_deadzone < 0.0:
            raise ValueError("yaw_to_dx_pixels must be > 0 and deadzone >= 0")
        if self.move_mode not in ("hold_forward", "ground_click"):
            raise ValueError("move_mode must be hold_forward or ground_click")
        if len(self.skill_keys) < 1:
            raise ValueError("skill_keys must not be empty")
        if self.watchdog_timeout_ms < 1:
            raise ValueError("watchdog_timeout_ms must be >= 1")

    def skill_key(self, slot: int) -> str:
        if slot < 1 or slot > len(self.skill_keys):
            raise ValueError(f"skill slot {slot} out of range")
        return self.skill_keys[slot - 1]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["measured_on_client"] = False
        payload["live_input"] = False
        return payload
