"""Synthetic combat arena. No client, no pcap, not Frozen 60."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from l2_brain.contracts import EncodedVisual, MotorIntent, Observation, ValidityMask
from l2_brain.io.actions import GameAction, SkillActivate, TargetSelect
from l2_brain.sim.world import wrap
from l2_brain.telemetry.events import CombatAction, EntityDefeated, HealthUpdate, RangeCue, TargetState
from l2_brain.telemetry.hub import TelemetryHub

DUMMY_ID = 1
ATTACK_RANGE_M = 1.8
HIT_DAMAGE = 25.0
DUMMY_MAX_HP = 100.0
SELECT_MIN_CONF = 0.3
ATTACK_KEY = "F2"


@dataclass(slots=True)
class CombatSnapshot:
    tick: int
    dummy_hp: float
    targeted: bool
    dummy_alive: bool
    distance_m: float
    damage_total: float
    outcome: str
    last_hit_confirmed: bool


class CombatArena:
    """One dummy, privileged range on the hub only."""

    name = "combat_dummy_v0"

    def __init__(
        self,
        hub: TelemetryHub,
        *,
        dummy_xy: tuple[float, float] = (9.0, 0.0),
        max_steps: int = 200,
        tick_hz: int = 20,
        max_speed: float = 0.12,
        max_turn: float = 0.18,
        fov_half: float = 0.6,
    ) -> None:
        self.hub = hub
        self.dummy_xy = dummy_xy
        self.max_steps = max_steps
        self.tick_hz = tick_hz
        self.max_speed = max_speed
        self.max_turn = max_turn
        self.fov_half = fov_half
        self._open = False
        self.tick = 0
        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0
        self.dummy_hp = DUMMY_MAX_HP
        self.targeted = False
        self.damage_total = 0.0
        self.last_hit_confirmed = False

    def initialize(self) -> None:
        self._open = True
        self.reset()

    def reset(self) -> Observation:
        self.tick = 0
        self.x, self.y = 0.0, 0.0
        self.yaw = 1.2
        self.dummy_hp = DUMMY_MAX_HP
        self.targeted = False
        self.damage_total = 0.0
        self.last_hit_confirmed = False
        self.hub.clear()
        obs = self.observe(1_000_000_000)
        self._publish(obs.timestamp_ns, damage=0.0, confirmed=False, attacked=False)
        return obs

    def close(self) -> None:
        self._open = False

    @property
    def distance_m(self) -> float:
        return math.hypot(self.dummy_xy[0] - self.x, self.dummy_xy[1] - self.y)

    @property
    def dummy_alive(self) -> bool:
        return self.dummy_hp > 0.0

    def observe(self, now_ns: int) -> Observation:
        bearing, conf = self._bearing_conf()
        return Observation(
            timestamp_ns=now_ns,
            frame_id=self.tick + 1,
            visual_features=EncodedVisual(0.0, max(conf, 0.0), 0.0, 0.0, conf * 0.4, conf),
            target_bearing=bearing,
            target_confidence=conf,
            motion_estimate=None,
            motion_confidence=0.0,
            telemetry=(),
            validity_mask=ValidityMask(True, True, True, False, True, False, False),
            previous_action=None,
        )

    def step(self, intent: MotorIntent, actions: list[GameAction], now_ns: int) -> CombatSnapshot:
        if not self._open:
            raise RuntimeError("CombatArena is closed")
        intent = intent.clipped()
        self._move(intent)
        self.tick += 1
        conf = self._bearing_conf()[1]
        selected = any(isinstance(item, TargetSelect) for item in actions)
        if selected and conf > SELECT_MIN_CONF and self.dummy_alive:
            self.targeted = True
        attacked = any(_is_f2(item) for item in actions)
        damage = 0.0
        confirmed = False
        if attacked:
            in_range = self.distance_m <= ATTACK_RANGE_M
            if self.targeted and in_range and self.dummy_alive:
                damage = HIT_DAMAGE
                confirmed = True
                self.dummy_hp = max(0.0, self.dummy_hp - damage)
                self.damage_total += damage
        self.last_hit_confirmed = confirmed
        obs = self.observe(now_ns)
        self._publish(now_ns, damage=damage, confirmed=confirmed, attacked=attacked)
        _ = obs
        return self.snapshot()

    def snapshot(self) -> CombatSnapshot:
        if not self.dummy_alive:
            outcome = "combat_success"
        elif self.tick >= self.max_steps:
            outcome = "timeout"
        else:
            outcome = "running"
        return CombatSnapshot(
            tick=self.tick,
            dummy_hp=self.dummy_hp,
            targeted=self.targeted,
            dummy_alive=self.dummy_alive,
            distance_m=self.distance_m,
            damage_total=self.damage_total,
            outcome=outcome,
            last_hit_confirmed=self.last_hit_confirmed,
        )

    def _move(self, intent: MotorIntent) -> None:
        if intent.stop == "fire":
            return
        self.yaw = wrap(self.yaw - intent.turn * self.max_turn)
        self.x += math.cos(self.yaw) * intent.forward * self.max_speed
        self.y += math.sin(self.yaw) * intent.forward * self.max_speed

    def _bearing_conf(self) -> tuple[float, float]:
        bearing = wrap(math.atan2(self.dummy_xy[1] - self.y, self.dummy_xy[0] - self.x) - self.yaw)
        visible = abs(bearing) <= self.fov_half
        conf = 0.85 if visible and self.dummy_alive else 0.05
        return bearing, conf

    def _publish(self, now_ns: int, *, damage: float, confirmed: bool, attacked: bool) -> None:
        src: Any = "sim_ground_truth"
        self.hub.publish(
            RangeCue(
                timestamp_ns=now_ns,
                source=src,
                confidence=1.0,
                distance_m=self.distance_m,
                in_range=self.distance_m <= ATTACK_RANGE_M,
            )
        )
        self.hub.publish(
            TargetState(
                timestamp_ns=now_ns,
                source=src,
                confidence=1.0,
                locked=self.targeted,
                target_id=DUMMY_ID if self.targeted else None,
                hp_percent=None if not self.dummy_alive else 100.0 * self.dummy_hp / DUMMY_MAX_HP,
            )
        )
        self.hub.publish(
            HealthUpdate(
                timestamp_ns=now_ns,
                source=src,
                confidence=1.0,
                current_hp=self.dummy_hp,
                max_hp=DUMMY_MAX_HP,
                delta=-damage,
                is_self=False,
            )
        )
        if attacked:
            self.hub.publish(
                CombatAction(
                    timestamp_ns=now_ns,
                    source=src,
                    confidence=1.0,
                    action_type="skill_f2",
                    confirmed=confirmed,
                    damage=damage,
                )
            )
        if not self.dummy_alive:
            self.hub.publish(
                EntityDefeated(
                    timestamp_ns=now_ns,
                    source=src,
                    confidence=1.0,
                    entity_id=DUMMY_ID,
                    is_target=self.targeted,
                    xp_gained=10 if self.targeted else 0,
                )
            )


def _is_f2(action: GameAction) -> bool:
    return isinstance(action, SkillActivate) and action.key == ATTACK_KEY


def snapshot_dict(snap: CombatSnapshot) -> dict[str, Any]:
    return asdict(snap)


def run_combat_episode(*, max_steps: int | None = None) -> dict[str, Any]:
    from l2_brain.control.tactical import TacticalCombatController
    from l2_brain.io import DryRunInputBackend, GameInputProfile

    hub = TelemetryHub()
    arena = CombatArena(hub)
    if max_steps is not None:
        arena.max_steps = max_steps
    profile = GameInputProfile(attack_key=ATTACK_KEY)
    backend = DryRunInputBackend(profile)
    ctl = TacticalCombatController(hub, profile)
    arena.initialize()
    ctl.initialize()
    now = 1_000_000_000
    period = int(1_000_000_000 / arena.tick_hz)
    obs = arena.reset()
    ticks_log: list[dict[str, Any]] = []
    snap = arena.snapshot()
    try:
        for _ in range(arena.max_steps):
            if snap.outcome != "running" and ctl.phase.value == "VICTORY":
                break
            intent = ctl.step(obs, now, 100_000_000)
            for action in ctl.last_actions:
                backend.send_action(action)
            snap = arena.step(intent, ctl.last_actions, now)
            ticks_log.append(
                {
                    "tick": snap.tick,
                    "phase": ctl.phase.value,
                    "distance_m": round(snap.distance_m, 3),
                    "dummy_hp": snap.dummy_hp,
                    "targeted": snap.targeted,
                    "hit": snap.last_hit_confirmed,
                    "outcome": snap.outcome,
                }
            )
            now += period
            obs = arena.observe(now)
            if snap.outcome == "combat_success":
                ctl.step(obs, now, 100_000_000)
                ticks_log.append(
                    {
                        "tick": snap.tick,
                        "phase": ctl.phase.value,
                        "distance_m": round(snap.distance_m, 3),
                        "dummy_hp": snap.dummy_hp,
                        "targeted": snap.targeted,
                        "hit": False,
                        "outcome": snap.outcome,
                    }
                )
                break
    finally:
        ctl.close()
        arena.close()
    return {
        "scenario": arena.name,
        "outcome": snap.outcome,
        "ticks": snap.tick,
        "damage_total": snap.damage_total,
        "dummy_killed": not snap.dummy_alive,
        "phases": list(ctl.history),
        "hid_sent": False,
        "dry_run": True,
        "privileged_in_observation": False,
        "transfer_claim": False,
        "ticks_log": ticks_log,
        "dry_run_n": len(backend.log),
    }
