"""L2 combat FSM on the synthetic stand. Does not use BaselineController."""

from __future__ import annotations

from enum import StrEnum

import numpy as np

from l2_brain.contracts import MotorIntent, Observation
from l2_brain.io.actions import GameAction
from l2_brain.io.decoder import IntentDecoder
from l2_brain.io.profile import GameInputProfile
from l2_brain.telemetry.events import EntityDefeated, RangeCue, TargetState
from l2_brain.telemetry.hub import TelemetryHub


class CombatPhase(StrEnum):
    SEEK = "SEEK"
    TARGET = "TARGET"
    APPROACH = "APPROACH"
    ATTACK = "ATTACK"
    VICTORY = "VICTORY"


class TacticalCombatController:
    """L1 seek on Observation + L2 FSM on TelemetryHub. Dry-run actions only."""

    name = "tactical_combat_v0"

    def __init__(self, hub: TelemetryHub, profile: GameInputProfile | None = None) -> None:
        self.hub = hub
        self.profile = profile or GameInputProfile(attack_key="F2")
        self.decoder = IntentDecoder(self.profile)
        self.phase = CombatPhase.SEEK
        self.history: list[str] = []
        self.last_actions: list[GameAction] = []
        self._open = False
        self.last_attack_ns = 0
        self.attack_gap_ms = 40

    def initialize(self) -> None:
        self._open = True
        self.reset_state()

    def reset_state(self) -> None:
        self.phase = CombatPhase.SEEK
        self.history = []
        self.last_actions = []
        self.last_attack_ns = 0

    def reset_weights(self) -> None:
        return None

    def close(self) -> None:
        self._open = False

    def step(self, observation: Observation, now_ns: int, intent_ttl_ns: int) -> MotorIntent:
        if not self._open:
            raise RuntimeError("TacticalCombatController is closed")
        self._advance(observation, now_ns)
        if self.phase not in self.history:
            self.history.append(self.phase)
        intent = self._intent(observation, now_ns + intent_ttl_ns)
        self.last_actions = self.decoder.decode(intent)
        return intent

    def _advance(self, observation: Observation, now_ns: int) -> None:
        dead = self.hub.get_latest(EntityDefeated)
        if dead is not None and dead.is_target:
            self.phase = CombatPhase.VICTORY
            return
        locked = False
        target = self.hub.get_latest(TargetState)
        if target is not None and not self.hub.is_stale(target, now_ns=now_ns):
            locked = target.locked
        rng = self.hub.get_latest(RangeCue)
        in_range = bool(rng is not None and not self.hub.is_stale(rng, now_ns=now_ns) and rng.in_range)
        conf = float(observation.target_confidence)
        if not locked:
            self.phase = CombatPhase.TARGET if conf > 0.3 else CombatPhase.SEEK
            return
        if not in_range:
            self.phase = CombatPhase.APPROACH
            return
        self.phase = CombatPhase.ATTACK

    def _intent(self, observation: Observation, until: int) -> MotorIntent:
        if self.phase is CombatPhase.VICTORY:
            return _intent(0.0, 0.0, stop=True, select=False, attack=False, until=until)
        bearing = float(observation.target_bearing or 0.0)
        turn = float(np.clip(-bearing / 0.6, -1.0, 1.0))
        if self.phase is CombatPhase.SEEK:
            return _intent(turn, 0.0, stop=False, select=False, attack=False, until=until)
        if self.phase is CombatPhase.TARGET:
            return _intent(turn, 0.0, stop=False, select=True, attack=False, until=until)
        if self.phase is CombatPhase.APPROACH:
            aligned = abs(bearing) < 0.35
            return _intent(turn, 0.85 if aligned else 0.15, stop=False, select=False, attack=False, until=until)
        can_attack = True
        if self.last_attack_ns and (until - self.last_attack_ns) / 1_000_000.0 < self.attack_gap_ms:
            can_attack = False
        if can_attack:
            self.last_attack_ns = until
        return _intent(turn, 0.0, stop=False, select=False, attack=can_attack, until=until)


def _intent(
    turn: float,
    forward: float,
    *,
    stop: bool,
    select: bool,
    attack: bool,
    until: int,
) -> MotorIntent:
    return MotorIntent(
        turn=turn,
        forward=0.0 if stop else forward,
        strafe=None,
        stop="fire" if stop else "idle",
        select_target="fire" if select else "idle",
        attack="fire" if attack else "idle",
        confidence=0.6,
        valid_until_ns=until,
    ).clipped()
