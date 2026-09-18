"""Pixel HUD → TelemetryHub. source=ui_vision. No HID. No sim GT replacement."""

from __future__ import annotations

from l2_brain.experiment.clocks import mono_ns
from l2_brain.telemetry.events import EntityDefeated, HealthUpdate, TargetState
from l2_brain.telemetry.hub import TelemetryHub
from l2_brain.vision.hud_parser import HUDParseResult

HP_MAX = 100.0
HP_NOISE = 0.5
UNKNOWN_ENTITY_ID = 0
# Last known target HP (0–100). Vanish at or below this counts as death.
DEFEAT_VANISH_HP = 8.0


class VisionTelemetryBridge:
    def __init__(self, hub: TelemetryHub, *, hp_noise: float = HP_NOISE) -> None:
        self.hub = hub
        self.hp_noise = hp_noise
        self._last_hp: float | None = None
        self._last_locked: bool | None = None
        self._last_target_hp: float | None = None
        self._defeat_emitted = False

    def publish(self, parsed: HUDParseResult, *, now_ns: int | None = None) -> int:
        if not parsed.valid:
            return 0
        now = mono_ns() if now_ns is None else now_ns
        hp = 0.0 if parsed.self_hp_ratio is None else parsed.self_hp_ratio * HP_MAX
        target_hp = None if parsed.target_hp_ratio is None else parsed.target_hp_ratio * HP_MAX
        n = 0
        if self._should_publish_health(hp):
            delta = 0.0 if self._last_hp is None else hp - self._last_hp
            self.hub.publish(
                HealthUpdate(
                    timestamp_ns=now,
                    source="ui_vision",
                    confidence=parsed.confidence,
                    current_hp=hp,
                    max_hp=HP_MAX,
                    delta=delta,
                    is_self=True,
                )
            )
            self._last_hp = hp
            n += 1
        if self._should_publish_defeat(parsed.target_locked, target_hp):
            self.hub.publish(
                EntityDefeated(
                    timestamp_ns=now,
                    source="ui_vision",
                    confidence=parsed.confidence,
                    entity_id=UNKNOWN_ENTITY_ID,
                    is_target=True,
                    xp_gained=0,
                )
            )
            self._defeat_emitted = True
            n += 1
        if parsed.target_locked and target_hp is not None and target_hp > self.hp_noise:
            self._defeat_emitted = False
        if self._should_publish_target(parsed.target_locked, target_hp):
            self.hub.publish(
                TargetState(
                    timestamp_ns=now,
                    source="ui_vision",
                    confidence=parsed.confidence,
                    locked=parsed.target_locked,
                    target_id=None,
                    hp_percent=target_hp,
                )
            )
            n += 1
        self._last_locked = parsed.target_locked
        self._last_target_hp = target_hp
        return n

    def _should_publish_health(self, hp: float) -> bool:
        if self._last_hp is None:
            return True
        return abs(hp - self._last_hp) >= self.hp_noise

    def _should_publish_target(self, locked: bool, target_hp: float | None) -> bool:
        if self._last_locked is None or locked != self._last_locked:
            return True
        if target_hp is None and self._last_target_hp is None:
            return False
        if target_hp is None or self._last_target_hp is None:
            return True
        return abs(target_hp - self._last_target_hp) >= self.hp_noise

    def _was_alive(self) -> bool:
        return (
            self._last_locked is True
            and self._last_target_hp is not None
            and self._last_target_hp > self.hp_noise
        )

    def _should_publish_defeat(self, locked: bool, target_hp: float | None) -> bool:
        if self._defeat_emitted:
            return False
        dead_visible = (
            locked
            and target_hp is not None
            and target_hp <= self.hp_noise
            and self._was_alive()
        )
        vanished_dead = (
            not locked
            and self._last_locked is True
            and self._last_target_hp is not None
            and self._last_target_hp <= DEFEAT_VANISH_HP
        )
        return dead_visible or vanished_dead
