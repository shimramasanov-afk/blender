from __future__ import annotations

from l2_brain.contracts import MotorIntent
from l2_brain.io.actions import (
    CameraRotate,
    EmergencyStop,
    GameAction,
    GroundClick,
    HoldKey,
    MouseButton,
    SkillActivate,
    TargetMethod,
    TargetSelect,
)
from l2_brain.io.profile import GameInputProfile


class IntentDecoder:
    """MotorIntent → discrete GameAction. Does not talk to HID."""

    def __init__(self, profile: GameInputProfile | None = None) -> None:
        self.profile = profile or GameInputProfile()

    def decode(self, intent: MotorIntent) -> list[GameAction]:
        intent = intent.clipped()
        if intent.stop == "fire":
            return [EmergencyStop(reason="intent.stop")]
        actions: list[GameAction] = []
        if abs(intent.turn) >= self.profile.yaw_deadzone:
            dx = int(round(intent.turn * self.profile.yaw_to_dx_pixels))
            if dx != 0:
                actions.append(CameraRotate(dx_pixels=dx, dy_pixels=0))
        if intent.forward > 0.5:
            actions.append(self._move())
        if intent.select_target == "fire":
            actions.append(TargetSelect(method=TargetMethod.NEXT_HOTKEY, coords=None))
        if intent.attack == "fire":
            actions.append(
                SkillActivate(slot=1, key=self.profile.attack_key, duration_ms=self.profile.press_duration_ms)
            )
        return actions

    def _move(self) -> GameAction:
        if self.profile.move_mode == "ground_click":
            x, y = self.profile.ground_click_xy
            return GroundClick(x=x, y=y, button=MouseButton.LEFT)
        return HoldKey(key=self.profile.move_forward_key, duration_ms=0)
