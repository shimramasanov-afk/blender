"""Multi-dummy spot. No client, no pcap, not Frozen 60."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from l2_brain.contracts import EncodedVisual, MotorIntent, Observation, ValidityMask
from l2_brain.io.actions import GameAction, Pickup, SkillActivate, TargetSelect
from l2_brain.sim.world import wrap
from l2_brain.telemetry.events import (
    CombatAction,
    CycleCompleted,
    EntityDefeated,
    HealthUpdate,
    LootCollected,
    LootSpawned,
    RangeCue,
    TargetState,
)
from l2_brain.telemetry.hub import TelemetryHub

ATTACK_RANGE_M = 1.8
PICKUP_RANGE_M = 1.2
HIT_DAMAGE = 25.0
DUMMY_MAX_HP = 100.0
SELECT_MIN_CONF = 0.3
ATTACK_KEY = "F2"
LOOT_LIFE_TICKS = 30
RESPAWN_TICKS = 20
ARENA_M = 20.0
N_DUMMIES = 3


@dataclass(slots=True)
class Dummy:
    entity_id: int
    x: float
    y: float
    hp: float = DUMMY_MAX_HP
    alive: bool = True
    dead_tick: int | None = None


@dataclass(slots=True)
class LootDrop:
    entity_id: int
    dummy_id: int
    x: float
    y: float
    spawn_tick: int
    collected: bool = False


@dataclass(slots=True)
class SpotSnapshot:
    tick: int
    kills: int
    loot_collected: int
    targeted_id: int | None
    dummy_alive: int
    loot_alive: int
    outcome: str
    last_hit_confirmed: bool
    last_pickup: int | None


class SpotArena:
    """Three respawning dummies. Privileged range stays on the hub."""

    name = "multi_dummy_arena_v0"

    def __init__(
        self,
        hub: TelemetryHub,
        *,
        seed: int = 0,
        max_steps: int = 250,
        tick_hz: int = 20,
        max_speed: float = 0.12,
        max_turn: float = 0.18,
        fov_half: float = 0.6,
        spawn_radius: tuple[float, float] = (3.6, 5.2),
        loot_offset: tuple[float, float] = (0.0, 0.0),
        world: float = ARENA_M,
    ) -> None:
        self.hub = hub
        self.seed = seed
        self.max_steps = max_steps
        self.tick_hz = tick_hz
        self.max_speed = max_speed
        self.max_turn = max_turn
        self.fov_half = fov_half
        self.spawn_radius = spawn_radius
        self.loot_offset = loot_offset
        self.world = world
        self.rng = np.random.default_rng(seed)
        self._open = False
        self.tick = 0
        self.x = world * 0.5
        self.y = world * 0.5
        self.yaw = 2.4
        self.dummies: list[Dummy] = []
        self.loot: list[LootDrop] = []
        self.targeted_id: int | None = None
        self.kills = 0
        self.loot_collected = 0
        self.last_hit_confirmed = False
        self.last_pickup: int | None = None
        self._loot_seq = 0
        self._defeated: set[int] = set()

    def initialize(self) -> None:
        self._open = True
        self.reset()

    def reset(self) -> Observation:
        self.rng = np.random.default_rng(self.seed)
        self.tick = 0
        self.x = self.world * 0.5
        self.y = self.world * 0.5
        self.yaw = 2.4
        self.targeted_id = None
        self.kills = 0
        self.loot_collected = 0
        self.last_hit_confirmed = False
        self.last_pickup = None
        self._loot_seq = 0
        self._defeated.clear()
        self.loot = []
        self.dummies = [Dummy(i + 1, 0.0, 0.0) for i in range(N_DUMMIES)]
        for dummy in self.dummies:
            dummy.x, dummy.y = self._place(exclude=dummy.entity_id)
        self.hub.clear()
        obs = self.observe(1_000_000_000)
        self._publish(obs.timestamp_ns, damage=0.0, attacked=False)
        return obs

    def close(self) -> None:
        self._open = False

    def observe(self, now_ns: int) -> Observation:
        bearing, conf, _kind = self._sight()
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

    def step(self, intent: MotorIntent, actions: list[GameAction], now_ns: int) -> SpotSnapshot:
        if not self._open:
            raise RuntimeError("SpotArena is closed")
        intent = intent.clipped()
        self._move(intent)
        self.tick += 1
        self.last_hit_confirmed = False
        self.last_pickup = None
        conf = self._sight()[1]
        if any(isinstance(item, TargetSelect) for item in actions) and conf > SELECT_MIN_CONF:
            visible = self._nearest_visible_dummy()
            if visible is not None:
                self.targeted_id = visible.entity_id
        attacked = any(_is_f2(item) for item in actions)
        damage = 0.0
        if attacked:
            dummy = self._by_id(self.targeted_id)
            if dummy is not None and dummy.alive and self._dist(dummy.x, dummy.y) <= ATTACK_RANGE_M:
                damage = HIT_DAMAGE
                dummy.hp = max(0.0, dummy.hp - damage)
                self.last_hit_confirmed = True
                if dummy.hp <= 0.0:
                    self._kill(dummy, now_ns)
        for item in actions:
            if isinstance(item, Pickup):
                self._try_pickup(item.entity_id, now_ns)
        self._age_loot()
        self._respawn()
        self._publish(now_ns, damage=damage, attacked=attacked)
        return self.snapshot()

    def snapshot(self) -> SpotSnapshot:
        if self.kills >= 3:
            outcome = "spot_loop_ok"
        elif self.tick >= self.max_steps:
            outcome = "timeout"
        else:
            outcome = "running"
        return SpotSnapshot(
            tick=self.tick,
            kills=self.kills,
            loot_collected=self.loot_collected,
            targeted_id=self.targeted_id,
            dummy_alive=sum(1 for dummy in self.dummies if dummy.alive),
            loot_alive=sum(1 for drop in self.loot if not drop.collected),
            outcome=outcome,
            last_hit_confirmed=self.last_hit_confirmed,
            last_pickup=self.last_pickup,
        )

    def clear_target(self) -> None:
        self.targeted_id = None

    def nearest_loot_id(self) -> int | None:
        drop = self._nearest_loot()
        return None if drop is None else drop.entity_id

    def _kill(self, dummy: Dummy, now_ns: int) -> None:
        dummy.alive = False
        dummy.dead_tick = self.tick
        self.kills += 1
        self._loot_seq += 1
        drop = LootDrop(
            entity_id=100 + self._loot_seq,
            dummy_id=dummy.entity_id,
            x=self._clip(dummy.x + self.loot_offset[0]),
            y=self._clip(dummy.y + self.loot_offset[1]),
            spawn_tick=self.tick,
        )
        self.loot.append(drop)
        src: Any = "sim_ground_truth"
        self.hub.publish(
            LootSpawned(
                timestamp_ns=now_ns,
                source=src,
                confidence=1.0,
                x=drop.x,
                y=drop.y,
                entity_id=drop.entity_id,
            )
        )
        self.hub.publish(
            EntityDefeated(
                timestamp_ns=now_ns,
                source=src,
                confidence=1.0,
                entity_id=dummy.entity_id,
                is_target=self.targeted_id == dummy.entity_id,
                xp_gained=10,
            )
        )

    def _try_pickup(self, entity_id: int, now_ns: int) -> None:
        for drop in self.loot:
            if drop.entity_id != entity_id or drop.collected:
                continue
            if self._dist(drop.x, drop.y) > PICKUP_RANGE_M:
                return
            drop.collected = True
            self.loot_collected += 1
            self.last_pickup = entity_id
            self.hub.publish(
                LootCollected(
                    timestamp_ns=now_ns,
                    source="sim_ground_truth",
                    confidence=1.0,
                    entity_id=entity_id,
                )
            )
            return

    def publish_cycle(self, now_ns: int) -> None:
        self.hub.publish(
            CycleCompleted(
                timestamp_ns=now_ns,
                source="sim_ground_truth",
                confidence=1.0,
                kills_count=self.kills,
                loot_count=self.loot_collected,
                total_ticks=self.tick,
            )
        )

    def _age_loot(self) -> None:
        keep: list[LootDrop] = []
        for drop in self.loot:
            if drop.collected:
                continue
            if self.tick - drop.spawn_tick >= LOOT_LIFE_TICKS:
                continue
            keep.append(drop)
        self.loot = keep

    def _respawn(self) -> None:
        for dummy in self.dummies:
            if dummy.alive or dummy.dead_tick is None:
                continue
            if self.tick - dummy.dead_tick < RESPAWN_TICKS:
                continue
            dummy.x, dummy.y = self._place(exclude=dummy.entity_id)
            dummy.hp = DUMMY_MAX_HP
            dummy.alive = True
            dummy.dead_tick = None

    def _move(self, intent: MotorIntent) -> None:
        if intent.stop == "fire":
            return
        self.yaw = wrap(self.yaw - intent.turn * self.max_turn)
        self.x = self._clip(self.x + math.cos(self.yaw) * intent.forward * self.max_speed)
        self.y = self._clip(self.y + math.sin(self.yaw) * intent.forward * self.max_speed)

    def _sight(self) -> tuple[float, float, str]:
        locked = self._by_id(self.targeted_id)
        if locked is not None and locked.alive:
            bearing = self._bearing(locked.x, locked.y)
            visible = abs(bearing) <= self.fov_half
            return bearing, 0.85 if visible else 0.55, "dummy"
        dummy = self._nearest_visible_dummy()
        if dummy is not None:
            return self._bearing(dummy.x, dummy.y), 0.85, "dummy"
        drop = self._nearest_visible_loot()
        if drop is not None:
            return self._bearing(drop.x, drop.y), 0.70, "loot"
        return 0.0, 0.05, "none"

    def _nearest_visible_dummy(self) -> Dummy | None:
        best: Dummy | None = None
        best_d = 1e9
        for dummy in self.dummies:
            if not dummy.alive:
                continue
            bearing = self._bearing(dummy.x, dummy.y)
            if abs(bearing) > self.fov_half:
                continue
            dist = self._dist(dummy.x, dummy.y)
            if dist < best_d:
                best, best_d = dummy, dist
        return best

    def _nearest_loot(self) -> LootDrop | None:
        alive = [drop for drop in self.loot if not drop.collected]
        if not alive:
            return None
        return min(alive, key=lambda drop: self._dist(drop.x, drop.y))

    def _nearest_visible_loot(self) -> LootDrop | None:
        best: LootDrop | None = None
        best_d = 1e9
        for drop in self.loot:
            if drop.collected:
                continue
            if abs(self._bearing(drop.x, drop.y)) > self.fov_half:
                continue
            dist = self._dist(drop.x, drop.y)
            if dist < best_d:
                best, best_d = drop, dist
        return best

    def _publish(self, now_ns: int, *, damage: float, attacked: bool) -> None:
        src: Any = "sim_ground_truth"
        subject_xy, in_range, hp, locked = self._subject()
        dist = self._dist(*subject_xy) if subject_xy is not None else 99.0
        self.hub.publish(
            RangeCue(
                timestamp_ns=now_ns,
                source=src,
                confidence=1.0,
                distance_m=dist,
                in_range=in_range,
            )
        )
        self.hub.publish(
            TargetState(
                timestamp_ns=now_ns,
                source=src,
                confidence=1.0,
                locked=locked,
                target_id=self.targeted_id,
                hp_percent=hp,
            )
        )
        dummy = self._by_id(self.targeted_id)
        if dummy is not None:
            self.hub.publish(
                HealthUpdate(
                    timestamp_ns=now_ns,
                    source=src,
                    confidence=1.0,
                    current_hp=dummy.hp,
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
                    confirmed=self.last_hit_confirmed,
                    damage=damage,
                )
            )

    def _subject(self) -> tuple[tuple[float, float] | None, bool, float | None, bool]:
        dummy = self._by_id(self.targeted_id)
        if dummy is not None and dummy.alive:
            dist = self._dist(dummy.x, dummy.y)
            return (dummy.x, dummy.y), dist <= ATTACK_RANGE_M, 100.0 * dummy.hp / DUMMY_MAX_HP, True
        drop = self._nearest_loot()
        if drop is not None:
            return (drop.x, drop.y), self._dist(drop.x, drop.y) <= PICKUP_RANGE_M, None, False
        visible = self._nearest_visible_dummy()
        if visible is not None:
            return (visible.x, visible.y), False, 100.0, False
        return None, False, None, False

    def _place(self, *, exclude: int) -> tuple[float, float]:
        lo, hi = self.spawn_radius
        others = [dummy for dummy in self.dummies if dummy.entity_id != exclude and dummy.alive]
        for _ in range(48):
            ang = float(self.rng.uniform(-math.pi, math.pi))
            radius = float(self.rng.uniform(lo, hi))
            x = self._clip(self.x + math.cos(ang) * radius)
            y = self._clip(self.y + math.sin(ang) * radius)
            if all(math.hypot(dummy.x - x, dummy.y - y) >= 1.4 for dummy in others):
                return x, y
        return self._clip(self.x + lo), self._clip(self.y)

    def _by_id(self, entity_id: int | None) -> Dummy | None:
        if entity_id is None:
            return None
        for dummy in self.dummies:
            if dummy.entity_id == entity_id:
                return dummy
        return None

    def _bearing(self, x: float, y: float) -> float:
        return wrap(math.atan2(y - self.y, x - self.x) - self.yaw)

    def _dist(self, x: float, y: float) -> float:
        return math.hypot(x - self.x, y - self.y)

    def _clip(self, value: float) -> float:
        return min(self.world - 0.5, max(0.5, value))


def _is_f2(action: GameAction) -> bool:
    return isinstance(action, SkillActivate) and action.key == ATTACK_KEY


def run_spot_loop(
    *,
    ticks: int = 250,
    seed: int = 0,
    spawn_radius: tuple[float, float] = (3.6, 5.2),
    loot_offset: tuple[float, float] = (0.0, 0.0),
    max_approach_ticks: int = 60,
    max_combat_ticks: int = 40,
    max_loot_ticks: int = 12,
) -> dict[str, Any]:
    from l2_brain.control.spot_agent import SpotAutonomousAgent
    from l2_brain.io import DryRunInputBackend, GameInputProfile

    hub = TelemetryHub()
    arena = SpotArena(
        hub,
        seed=seed,
        max_steps=ticks,
        spawn_radius=spawn_radius,
        loot_offset=loot_offset,
    )
    profile = GameInputProfile(attack_key=ATTACK_KEY)
    backend = DryRunInputBackend(profile)
    agent = SpotAutonomousAgent(
        hub,
        profile,
        max_approach_ticks=max_approach_ticks,
        max_combat_ticks=max_combat_ticks,
        max_loot_ticks=max_loot_ticks,
    )
    arena.initialize()
    agent.initialize()
    now = 1_000_000_000
    period = int(1_000_000_000 / arena.tick_hz)
    obs = arena.reset()
    log: list[dict[str, Any]] = []
    snap = arena.snapshot()
    try:
        for _ in range(arena.max_steps):
            intent = agent.step(obs, now, 100_000_000)
            for action in agent.last_actions:
                backend.send_action(action)
            snap = arena.step(intent, agent.last_actions, now)
            if agent.consume_cycle():
                arena.publish_cycle(now)
            if agent.phase.value == "RESET":
                arena.clear_target()
            log.append(
                {
                    "tick": snap.tick,
                    "phase": agent.phase.value,
                    "kills": snap.kills,
                    "loot": snap.loot_collected,
                    "targeted": snap.targeted_id,
                    "hit": snap.last_hit_confirmed,
                    "pickup": snap.last_pickup,
                    "reason": agent.last_reason,
                }
            )
            now += period
            obs = arena.observe(now)
    finally:
        agent.close()
        arena.close()
    phases = _unique_order(agent.history)
    return {
        "scenario": arena.name,
        "outcome": snap.outcome,
        "ticks": snap.tick,
        "kills": snap.kills,
        "loot_collected": snap.loot_collected,
        "max_kill_streak": agent.max_streak,
        "phases": phases,
        "phase_trace": [row["phase"] for row in log],
        "max_loot_streak": _max_streak(log, "LOOT"),
        "max_approach_streak": _max_streak(log, "APPROACH"),
        "max_combat_streak": _max_streak(log, "COMBAT"),
        "watchdog_resets": agent.watchdog_resets,
        "hid_sent": False,
        "dry_run": True,
        "privileged_in_observation": False,
        "transfer_claim": False,
        "dry_run_n": len(backend.log),
        "ticks_log": log,
    }


def _unique_order(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _max_streak(log: list[dict[str, Any]], phase: str) -> int:
    best = cur = 0
    for row in log:
        if row["phase"] == phase:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best
