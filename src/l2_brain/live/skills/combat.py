from __future__ import annotations

from l2_brain.io.actions import HoldKey, SkillActivate
from l2_brain.live.s4_probe import ENGAGE_F2_GAP_S
from l2_brain.live.skills.base import BaseSkill
from l2_brain.live.skills.dispatch import send_live
from l2_brain.live.skills.result import SkillResult, SkillStatus
from l2_brain.live.spot_loop import (
    COMBAT_MAX_S,
    COMBAT_NO_DAMAGE_S,
    L1_COOLDOWN_S,
    L1_FLOW_STATIC_MAX,
    L1_MAX_PER_BURST,
    LOOT_GAP_S,
    LOOT_TAPS,
    PEEL_MS,
    SELF_HP_ABORT,
    VANISH_HP,
    should_l1_unjam,
)
from l2_brain.live.world_state import WorldState

BLIND_ENGAGE_S = 5.0


class AttackTarget(BaseSkill):
    """Combat F2. Tick watches WorldState; does not loop 25s inside start()."""

    name = "attack_target"

    def __init__(self, *, engage_f2: bool = True, require_lock: bool = True) -> None:
        super().__init__()
        self._engage_f2 = bool(engage_f2)
        self._require_lock = bool(require_lock)
        self._started_ns: int | None = None
        self._last_hp: float | None = None
        self._last_drop_ns: int | None = None
        self._last_l1_ns: int | None = None
        self._f2_sent = 0
        self._static_ticks = 0
        self._burst = 0
        self._saw_lock = False

    def can_start(self, state: WorldState) -> bool:
        if not super().can_start(state):
            return False
        if self._require_lock:
            if state.target_locked is not True:
                return False
            if state.target_dead is True:
                return False
        if state.self_hp is not None and state.self_hp < SELF_HP_ABORT:
            return False
        return True

    def start(self, context: object, state: WorldState) -> SkillResult:
        if not self.can_start(state):
            return self._fail("precondition")
        if self._engage_f2 and not self._tap_f2(context):
            return self._fail(str(context.log.get("aborted") or "f2_failed"))
        now = context.clock()
        self._started_ns = now
        self._last_hp = state.target_hp
        self._last_drop_ns = now
        self._last_l1_ns = now
        self._static_ticks = 0
        self._burst = 0
        self._saw_lock = self._living_lock(state)
        return self._run("engaged", target_hp=state.target_hp, f2_sent=self._f2_sent)

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self._status is not SkillStatus.RUNNING:
            return SkillResult(self._status, reason="not_running")
        if not state.focus_ok:
            return self.cancel(context, "focus_lost")
        if not state.capture_ok:
            return self.cancel(context, "capture_lost")
        if state.self_hp is not None and state.self_hp < SELF_HP_ABORT:
            return self._fail("self_hp_low", self_hp=state.self_hp)
        if self._living_lock(state):
            self._saw_lock = True
        if self._killed(state):
            return self._ok("target_dead", target_hp=state.target_hp, f2_sent=self._f2_sent)
        now = context.clock()
        elapsed = 0.0 if self._started_ns is None else (now - self._started_ns) / 1e9
        if not self._require_lock and not self._saw_lock and elapsed >= BLIND_ENGAGE_S:
            return self._fail("no_hud_lock", f2_sent=self._f2_sent)
        if elapsed >= COMBAT_MAX_S:
            return self._fail("combat_timeout", target_hp=state.target_hp, f2_sent=self._f2_sent)
        if state.target_locked is False and not self._killed(state):
            if self._require_lock:
                return self._fail("target_lost", f2_sent=self._f2_sent)
        hp = state.target_hp
        if self._last_hp is not None and hp is not None and self._last_hp - hp > 0:
            self._last_drop_ns = now
            self._static_ticks = 0
        self._last_hp = hp if hp is not None else self._last_hp
        mag = state.motion_magnitude
        if mag is not None and mag < L1_FLOW_STATIC_MAX:
            self._static_ticks += 1
        elif mag is not None:
            self._static_ticks = 0
        no_dmg_s = 0.0 if self._last_drop_ns is None else (now - self._last_drop_ns) / 1e9
        if (
            self._burst < L1_MAX_PER_BURST
            and self._last_l1_ns is not None
            and (now - self._last_l1_ns) / 1e9 >= L1_COOLDOWN_S
            and should_l1_unjam(
                f2_active_s=no_dmg_s,
                target_damaged=False,
                static_ticks=self._static_ticks,
            )
        ):
            direction = "right" if (self._burst + 1) % 2 == 1 else "left"
            key = f"{direction}_arrow"
            down = send_live(
                context.backend,
                HoldKey(key=key, duration_ms=PEEL_MS, state="down"),
                context.log,
            )
            if down is None:
                return self._fail(str(context.log.get("aborted") or "l1_peel_failed"))
            up = send_live(context.backend, HoldKey(key=key, duration_ms=0, state="up"), context.log)
            if up is None:
                return self._fail(str(context.log.get("aborted") or "l1_peel_failed"))
            self._burst += 1
            self._last_l1_ns = now
            self._static_ticks = 0
            return self._run("l1_peel", key=key, duration_ms=PEEL_MS, burst=self._burst, target_hp=state.target_hp)
        if self._last_drop_ns is not None and no_dmg_s >= COMBAT_NO_DAMAGE_S:
            if not self._tap_f2(context):
                return self._fail(str(context.log.get("aborted") or "f2_retry_failed"))
            self._last_drop_ns = now
        return self._run("in_combat", target_hp=state.target_hp, f2_sent=self._f2_sent)

    def _tap_f2(self, context: object) -> bool:
        ev = send_live(context.backend, SkillActivate(slot=2, key="F2", duration_ms=40), context.log)
        if ev is None:
            return False
        self._f2_sent += 1
        if self._f2_sent == 1:
            context.sleeper(ENGAGE_F2_GAP_S)
            ev2 = send_live(context.backend, SkillActivate(slot=2, key="F2", duration_ms=40), context.log)
            if ev2 is None:
                return False
            self._f2_sent += 1
        return True

    def _living_lock(self, state: WorldState) -> bool:
        if state.target_locked is not True or state.target_dead is True:
            return False
        return state.target_hp is None or state.target_hp > 0.0

    def _killed(self, state: WorldState) -> bool:
        if not self._saw_lock:
            return False
        if state.target_dead is True:
            return True
        if state.target_hp is not None and state.target_hp <= 0.0:
            return True
        vanished = state.target_locked is False and self._last_hp is not None and self._last_hp <= VANISH_HP
        return vanished


class LootTarget(BaseSkill):
    """F3 × LOOT_TAPS. SUCCESS = loot input sequence completed, not inventory confirm."""

    name = "loot_target"

    def __init__(self) -> None:
        super().__init__()
        self._taps = 0
        self._wait_until: int | None = None

    def start(self, context: object, state: WorldState) -> SkillResult:
        if not state.focus_ok:
            return self._fail("precondition")
        self._taps = 0
        self._wait_until = None
        return self._tap(context)

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self._status is not SkillStatus.RUNNING:
            return SkillResult(self._status, reason="not_running")
        if not state.focus_ok:
            return self.cancel(context, "focus_lost")
        now = context.clock()
        if self._wait_until is not None and now < self._wait_until:
            return self._run("loot_gap", taps=self._taps)
        if self._taps >= LOOT_TAPS:
            return self._ok("loot_input_sequence_completed", taps=self._taps, inventory_confirmed=False)
        return self._tap(context)

    def _tap(self, context: object) -> SkillResult:
        ev = send_live(context.backend, SkillActivate(slot=3, key="F3", duration_ms=40), context.log)
        if ev is None:
            return self._fail(str(context.log.get("aborted") or "f3_failed"), taps=self._taps)
        self._taps += 1
        self._wait_until = context.clock() + int(LOOT_GAP_S * 1_000_000_000)
        if self._taps >= LOOT_TAPS:
            return self._ok("loot_input_sequence_completed", taps=self._taps, inventory_confirmed=False)
        return self._run("loot_tap", taps=self._taps)
