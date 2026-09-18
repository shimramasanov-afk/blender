"""L2 spot FSM. L1 is snn_v1. Does not modify BaselineController."""

from __future__ import annotations

from enum import StrEnum

import numpy as np

from l2_brain.contracts import MotorIntent, Observation
from l2_brain.control.snn import LIFConfig, SNNController
from l2_brain.io.actions import GameAction, Pickup
from l2_brain.io.decoder import IntentDecoder
from l2_brain.io.profile import GameInputProfile
from l2_brain.telemetry.events import EntityDefeated, LootCollected, LootSpawned, RangeCue, TargetState
from l2_brain.telemetry.hub import TelemetryHub


class SpotPhase(StrEnum):
    SCAN = "SCAN"
    TARGET = "TARGET"
    APPROACH = "APPROACH"
    COMBAT = "COMBAT"
    LOOT = "LOOT"
    RESET = "RESET"


class SpotAutonomousAgent:
    """SCAN→TARGET→APPROACH→COMBAT→LOOT→RESET. Watchdogs cut hangs."""

    name = "spot_autonomous_v0"

    def __init__(
        self,
        hub: TelemetryHub,
        profile: GameInputProfile | None = None,
        *,
        max_scan_ticks: int = 20,
        max_approach_ticks: int = 60,
        max_combat_ticks: int = 40,
        max_loot_ticks: int = 12,
        attack_gap_ms: int = 40,
    ) -> None:
        self.hub = hub
        self.profile = profile or GameInputProfile(attack_key="F2")
        self.decoder = IntentDecoder(self.profile)
        self.l1 = SNNController(LIFConfig(seed=0))
        self.max_scan_ticks = max_scan_ticks
        self.max_approach_ticks = max_approach_ticks
        self.max_combat_ticks = max_combat_ticks
        self.max_loot_ticks = max_loot_ticks
        self.attack_gap_ms = attack_gap_ms
        self.phase = SpotPhase.SCAN
        self.history: list[str] = []
        self.last_actions: list[GameAction] = []
        self.last_reason = "boot"
        self._phase_ticks = 0
        self._scan_ticks = 0
        self.last_attack_ns = 0
        self._open = False
        self.kills_seen = 0
        self.streak = 0
        self.max_streak = 0
        self.watchdog_resets = 0
        self._cycle_ready = False
        self._loot_id: int | None = None
        self._seen_defeat_ns: int | None = None

    def initialize(self) -> None:
        self._open = True
        self.l1.initialize()
        self.reset_state()

    def reset_state(self) -> None:
        self.phase = SpotPhase.SCAN
        self.history = [self.phase.value]
        self.last_actions = []
        self.last_reason = "boot"
        self._phase_ticks = 0
        self._scan_ticks = 0
        self.last_attack_ns = 0
        self.kills_seen = 0
        self.streak = 0
        self.max_streak = 0
        self.watchdog_resets = 0
        self._cycle_ready = False
        self._loot_id = None
        self._seen_defeat_ns = None
        self.l1.reset_state()

    def close(self) -> None:
        self._open = False
        self.l1.close()

    def consume_cycle(self) -> bool:
        ready = self._cycle_ready
        self._cycle_ready = False
        return ready

    def step(self, observation: Observation, now_ns: int, intent_ttl_ns: int) -> MotorIntent:
        if not self._open:
            raise RuntimeError("SpotAutonomousAgent is closed")
        prev = self.phase
        self._phase_ticks += 1
        self._advance(observation, now_ns)
        if self.phase is not prev:
            self.history.append(self.phase.value)
            self._phase_ticks = 0
        intent = self._intent(observation, now_ns, now_ns + intent_ttl_ns)
        self.last_actions = self.decoder.decode(intent)
        if self.phase is SpotPhase.LOOT and self._loot_id is not None:
            self.last_actions.append(Pickup(self._loot_id))
        return intent

    def _advance(self, observation: Observation, now_ns: int) -> None:
        # SCAN --conf--> TARGET --lock--> APPROACH --range--> COMBAT --kill--> LOOT --done--> RESET --> SCAN
        locked, in_range = self._tactical(now_ns)
        conf = float(observation.target_confidence)
        defeat = self._fresh_defeat()
        loot = self.hub.get_latest(LootSpawned)

        if self.phase is SpotPhase.RESET:
            self.phase = SpotPhase.SCAN
            self.last_reason = "scan"
            self._loot_id = None
            self._scan_ticks = 0
            return

        if self.phase is SpotPhase.SCAN:
            self._scan_ticks += 1
            if conf > 0.3:
                self.phase = SpotPhase.TARGET
                self.last_reason = "silhouette"
            return

        if self.phase is SpotPhase.TARGET:
            if locked:
                self.phase = SpotPhase.APPROACH
                self.last_reason = "lock"
            elif conf <= 0.3:
                self._watchdog("lost_silhouette")
            return

        if self.phase is SpotPhase.APPROACH:
            if defeat:
                self._enter_loot(loot)
                return
            if in_range:
                self.phase = SpotPhase.COMBAT
                self.last_reason = "in_range"
                return
            if self._phase_ticks >= self.max_approach_ticks:
                self._watchdog("approach_timeout")
            return

        if self.phase is SpotPhase.COMBAT:
            if defeat:
                self._enter_loot(loot)
                return
            if self._phase_ticks >= self.max_combat_ticks:
                self._watchdog("combat_timeout")
                return
            if not locked:
                self._watchdog("lost_lock")
            return

        if self.phase is SpotPhase.LOOT:
            got = self.hub.get_latest(LootCollected)
            collected = bool(got is not None and got.entity_id == self._loot_id)
            if collected or self._phase_ticks >= self.max_loot_ticks:
                self._cycle_ready = True
                self.phase = SpotPhase.RESET
                self.last_reason = "loot_done" if collected else "loot_timeout"
            return

    def _enter_loot(self, loot: LootSpawned | None) -> None:
        self.kills_seen += 1
        self.streak += 1
        self.max_streak = max(self.max_streak, self.streak)
        self._loot_id = loot.entity_id if loot is not None else None
        self.phase = SpotPhase.LOOT
        self.last_reason = "kill"

    def _watchdog(self, reason: str) -> None:
        self.watchdog_resets += 1
        self.streak = 0
        self.phase = SpotPhase.RESET
        self.last_reason = reason
        self._loot_id = None

    def _fresh_defeat(self) -> bool:
        dead = self.hub.get_latest(EntityDefeated)
        if dead is None or not dead.is_target:
            return False
        if dead.timestamp_ns == self._seen_defeat_ns:
            return False
        self._seen_defeat_ns = dead.timestamp_ns
        return True

    def _tactical(self, now_ns: int) -> tuple[bool, bool]:
        target = self.hub.get_latest(TargetState)
        locked = bool(
            target is not None and not self.hub.is_stale(target, now_ns=now_ns) and target.locked
        )
        rng = self.hub.get_latest(RangeCue)
        in_range = bool(rng is not None and not self.hub.is_stale(rng, now_ns=now_ns) and rng.in_range)
        return locked, in_range

    def _intent(self, observation: Observation, now_ns: int, until: int) -> MotorIntent:
        if self.phase is SpotPhase.RESET:
            return _intent(0.0, 0.0, stop=True, select=False, attack=False, until=until)
        if self.phase is SpotPhase.SCAN:
            shift = 0.35 if self._scan_ticks >= self.max_scan_ticks else 0.0
            if self._scan_ticks >= self.max_scan_ticks:
                self._scan_ticks = 0
            return _intent(0.85, shift, stop=False, select=False, attack=False, until=until)
        turn, forward = self._steer(observation, now_ns, until)
        if self.phase is SpotPhase.TARGET:
            return _intent(turn, 0.0, stop=False, select=True, attack=False, until=until)
        if self.phase is SpotPhase.APPROACH:
            return _intent(turn, forward, stop=False, select=False, attack=False, until=until)
        if self.phase is SpotPhase.COMBAT:
            can_attack = True
            if self.last_attack_ns and (until - self.last_attack_ns) / 1_000_000.0 < self.attack_gap_ms:
                can_attack = False
            if can_attack:
                self.last_attack_ns = until
            return _intent(turn, 0.0, stop=False, select=False, attack=can_attack, until=until)
        return _intent(turn, max(forward, 0.25), stop=False, select=False, attack=False, until=until)

    def _steer(self, observation: Observation, now_ns: int, until: int) -> tuple[float, float]:
        """L2 holds combat bearing; SNN supplies gait. Nav-calibrated SNN yaw ≠ atan2-yaw."""
        bearing = float(observation.target_bearing or 0.0)
        heading = float(np.clip(-bearing / 0.6, -1.0, 1.0))
        gait = self.l1.step(observation, now_ns, until - now_ns)
        aligned = abs(bearing) < 0.35
        forward = 0.85 if aligned else max(float(gait.forward), 0.20)
        return heading, forward


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
