from __future__ import annotations

from l2_brain.contracts import PRIVILEGED_OBSERVATION_FIELDS
from l2_brain.io.actions import SkillActivate, TargetMethod, TargetSelect
from l2_brain.sim.combat import ATTACK_KEY, CombatArena, run_combat_episode
from l2_brain.telemetry import CombatAction, HealthUpdate, TelemetryHub


def test_hub_ring_and_stale() -> None:
    hub = TelemetryHub(maxlen=64)
    now = 10**12
    first = HealthUpdate(now, "mock", 1.0, 100.0, 100.0, 0.0, True)
    hub.publish(first)
    assert hub.get_latest(HealthUpdate) is first
    assert hub.is_stale(first, threshold_ms=300, now_ns=now + 400_000_000)
    assert not hub.is_stale(first, threshold_ms=300, now_ns=now + 10_000_000)
    for i in range(70):
        hub.publish(HealthUpdate(now + i, "mock", 1.0, float(i), 100.0, -1.0, False))
    assert len(hub) == 64
    latest = hub.get_latest(HealthUpdate)
    assert latest is not None
    assert latest.current_hp == 69.0
    hub.clear()
    assert len(hub) == 0


def test_attack_out_of_range_does_not_damage() -> None:
    hub = TelemetryHub()
    arena = CombatArena(hub)
    arena.initialize()
    arena.reset()
    arena.yaw = 0.0
    now = 2_000_000_000
    from l2_brain.sim.environment import idle_intent

    idle = idle_intent(now)
    arena.step(idle, [TargetSelect(method=TargetMethod.NEXT_HOTKEY)], now)
    assert arena.targeted
    before = arena.dummy_hp
    snap = arena.step(idle, [SkillActivate(1, ATTACK_KEY, 40)], now + 50_000_000)
    assert snap.distance_m > 1.8
    assert snap.last_hit_confirmed is False
    assert arena.dummy_hp == before
    action = hub.get_latest(CombatAction)
    assert action is not None
    assert action.confirmed is False
    assert action.damage == 0.0
    arena.close()


def test_attack_without_target_select_blocked() -> None:
    hub = TelemetryHub()
    arena = CombatArena(hub)
    arena.initialize()
    arena.reset()
    arena.x, arena.y, arena.yaw = 7.3, 0.0, 0.0
    now = 3_000_000_000
    from l2_brain.sim.environment import idle_intent

    snap = arena.step(idle_intent(now), [SkillActivate(1, ATTACK_KEY, 40)], now)
    assert snap.distance_m <= 1.8
    assert snap.targeted is False
    assert snap.last_hit_confirmed is False
    assert snap.dummy_hp == 100.0
    arena.close()


def test_end_to_end_combat_dummy() -> None:
    report = run_combat_episode()
    assert report["outcome"] == "combat_success"
    assert report["dummy_killed"] is True
    assert report["damage_total"] >= 100.0
    assert report["hid_sent"] is False
    assert report["phases"] == ["SEEK", "TARGET", "APPROACH", "ATTACK", "VICTORY"]
    assert report["ticks"] <= 200
    assert report["privileged_in_observation"] is False


def test_observation_has_no_privileged_pose() -> None:
    hub = TelemetryHub()
    arena = CombatArena(hub)
    arena.initialize()
    obs = arena.reset()
    leaked = PRIVILEGED_OBSERVATION_FIELDS.intersection(obs.__dataclass_fields__)
    assert not leaked
    assert obs.telemetry == ()
    arena.close()
