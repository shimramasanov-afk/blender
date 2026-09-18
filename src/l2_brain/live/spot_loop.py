"""Live L1 encoder + L2 spot FSM. Hod 82. Not Frozen L1. Not farm."""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.bench.h8_latency_bench import summarize
from l2_brain.bench.live_motion_probe import flow_magnitude_midnear
from l2_brain.capture.profile import WindowProfile
from l2_brain.contracts import Frame
from l2_brain.experiment.clocks import mono_ns
from l2_brain.io.cgevent_backend import CGEventInputBackend
from l2_brain.io.focus import frontmost_app, is_allowed_frontmost
from l2_brain.live.s4_probe import (
    ENGAGE_DAMAGE_EPS,
    ENGAGE_HP_MIN,
    MULTI_LOOT_DROP_S,
    MULTI_RESET_S,
    SEARCH_HOLD_MAX_MS,
    SCKGrabber,
    TICK_S,
    _ms,
    s4_input_profile,
)
from l2_brain.telemetry.hub import TelemetryHub
from l2_brain.telemetry.vision_bridge import VisionTelemetryBridge
from l2_brain.vision.config import VisionConfig
from l2_brain.vision.encoder import NavigationEncoder
from l2_brain.vision.hud_parser import HUDParseResult, HUDParser

DEFAULT_PROFILE = Path("config/window_profiles/parallels_l2.json")
DEFAULT_OUT = Path("docs/evidence/live-s4/spot-series-10-stable.json")
KILL_CAP = 10
SCAN_F1 = 2
SCAN_S = 1.2
ROAM_FAIL_LIMIT = 15
ROAM_WALK_PULSES = 4
ROAM_UTURN_AFTER = 3
WALK_MS = 450
WALK_GAP_S = 0.05
ARROW_MS = 450
UTURN_ARROW_PULSES = 2
UTURN_WALK_PULSES = 3
UTURN_WALK_MS = 500
PEEL_MS = 350
L1_F2_STUCK_S = 3.0
L1_FLOW_STATIC_MAX = 0.01
L1_STATIC_TICKS = 6
L1_COOLDOWN_S = 2.0
L1_MAX_PER_BURST = 3
AGGRO_WINDOW = 5
AGGRO_DROP_VS_MEAN = 0.015
AGGRO_APPROACH_S = 2.5
AGGRO_COOLDOWN_S = 2.0
LOOT_TAPS = 3
LOOT_GAP_S = 0.35
LOOT_SETTLE_S = 0.40
COMBAT_NO_DAMAGE_S = 8.0
COMBAT_MAX_S = 25.0
SELF_HP_MIN = 0.30
SELF_HP_ABORT = 0.10
VANISH_HP = 0.08
SETTLE_S = 1.0

assert WALK_MS <= 800
assert UTURN_WALK_MS <= 800
assert WALK_MS <= SEARCH_HOLD_MAX_MS
assert UTURN_WALK_MS <= SEARCH_HOLD_MAX_MS
assert PEEL_MS <= SEARCH_HOLD_MAX_MS
assert ARROW_MS <= SEARCH_HOLD_MAX_MS


def should_aggro_interrupt(
    *,
    self_hp: float | None,
    prev_self_hps: Sequence[float],
    target_locked: bool,
    target_no_damage_s: float,
    drop_vs_mean: float = AGGRO_DROP_VS_MEAN,
    approach_s: float = AGGRO_APPROACH_S,
) -> bool:
    if self_hp is None or not prev_self_hps:
        return False
    mean_prev = float(sum(prev_self_hps)) / float(len(prev_self_hps))
    if mean_prev - self_hp < drop_vs_mean:
        return False
    if not target_locked:
        return True
    return target_no_damage_s > approach_s


def should_l1_unjam(
    *,
    f2_active_s: float,
    target_damaged: bool,
    static_ticks: int,
    f2_min_s: float = L1_F2_STUCK_S,
    static_need: int = L1_STATIC_TICKS,
) -> bool:
    if target_damaged:
        return False
    if f2_active_s <= f2_min_s:
        return False
    return static_ticks >= static_need


def _as_frame(image: np.ndarray, frame_id: int, ts_ns: int) -> Frame:
    return Frame(
        frame_id=int(frame_id),
        timestamp_capture_ns=int(ts_ns),
        timestamp_received_ns=int(ts_ns),
        width=int(image.shape[1]),
        height=int(image.shape[0]),
        pixel_format="rgb8",
        source_id="sck.window",
        image=np.ascontiguousarray(image),
    )


def run_integrated_spot(
    *,
    live: bool,
    danger_confirmed: bool,
    window_id: int | None = None,
    target_pid: int | None = None,
    profile_path: Path = DEFAULT_PROFILE,
    out_path: Path | None = DEFAULT_OUT,
    kills: int = KILL_CAP,
    runtime_validation: bool = False,
    timeout_s: float | None = None,
    grabber: Any | None = None,
    backend: CGEventInputBackend | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    now_ns: Callable[[], int] | None = None,
    focus_probe: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    clock = now_ns or mono_ns
    started = clock()
    kill_target = min(max(int(kills), 1), KILL_CAP)
    session_s = None if timeout_s is None else max(float(timeout_s), 1.0)
    steps: list[dict[str, Any]] = []
    payload: dict[str, Any] = {
        "ok": False,
        "s4_open": True,
        "spot_series": True,
        "integrated": True,
        "farm": False,
        "no_heal": True,
        "heal_sent": False,
        "live": bool(live and danger_confirmed),
        "hid_sent": False,
        "aborted": None,
        "window_id": window_id,
        "target_pid": target_pid,
        "timeout_s": session_s,
        "total_kills": 0,
        "kills_completed": 0,
        "roam_cycles": 0,
        "l1_stuck_triggers": 0,
        "l1_triggers": 0,
        "aggro_interrupts": 0,
        "aggro_triggers": 0,
        "u_turns_executed": 0,
        "u_turns": 0,
        "elapsed_time_sec": 0.0,
        "total_time_sec": 0.0,
        "avg_combat_duration_sec": None,
        "avg_combat_sec": None,
        "stuck_keys": 0,
        "frags": [],
        "flow_samples": [],
        "hotbar": {"F1": "/targetnext", "F2": "Attack", "F3": "Pickup"},
        "rotation_type": "keyboard_arrow",
        "walk": True,
        "target_locked": False,
        "target_killed": False,
        "entity_defeated": False,
        "loot_pickup_sent": False,
        "loot_actions_sent": 0,
        "f1_pulses": 0,
        "f2_pulses": 0,
        "stuck_keys_count": 0,
        "watchdog_tripped": False,
        "ticks": 0,
        "session_ms": 0.0,
        "steps": steps,
        "events": [],
        "observe_ms": [],
        "parse_ms": [],
        "encode_ms": [],
        "infer_ms": [],
        "act_ms": [],
        "runtime_validation": bool(runtime_validation),
        "architecture": "LiveRuntime",
        "runtime_used": True,
        "validation_id": "R2",
        "max_kills": kill_target,
        "skill_trace": [],
        "target_next_attempts": 0,
        "attack_skill_runs": 0,
        "attack_skill_success": 0,
        "attack_skill_failed": 0,
        "loot_skill_runs": 0,
        "f2_input_count": 0,
        "self_hp_start": None,
        "self_hp_min": None,
        "self_hp_end": None,
        "focus_lost": False,
        "capture_lost": False,
        "runtime_abort_reason": None,
        "release_all_called": False,
        "frozen_used": False,
        "snn_used": False,
        "malecns_used": False,
        "circuit_used": False,
        "validation_result": None,
        "elapsed_sec": 0.0,
    }
    if not live or not danger_confirmed:
        payload["aborted"] = "live_flags_required"
        return _finish_integrated(payload, out_path, clock, started, None, None)
    if grabber is None and (window_id is None or int(window_id) < 1):
        payload["aborted"] = "window_id_required"
        return _finish_integrated(payload, out_path, clock, started, None, None)

    parser = HUDParser.from_profile(profile_path)
    hub = TelemetryHub(maxlen=256)
    bridge = VisionTelemetryBridge(hub)
    win_profile = WindowProfile.load(profile_path) if Path(profile_path).exists() else None
    encoder = NavigationEncoder(VisionConfig(profile=win_profile))
    encoder.initialize()
    own_grabber = grabber is None
    own_backend = backend is None
    grabber = grabber or SCKGrabber(int(window_id or 0))
    if own_backend:
        pid = int(target_pid or 0)
        if pid < 1:
            info = frontmost_app()
            pid = int(info.pid) if info is not None else 0
        if pid < 1:
            payload["aborted"] = "no_target_pid"
            return _finish_integrated(payload, out_path, clock, started, None, encoder)
        payload["target_pid"] = pid
        backend = CGEventInputBackend(
            pid,
            live_confirmed=True,
            live_danger_confirmed=True,
            profile=s4_input_profile(),
            focus_probe=focus_probe or is_allowed_frontmost,
        )
    assert backend is not None
    focus = focus_probe or backend.check_window_focus
    frame_id = 0
    prev_obs = None
    last_l1_at = started
    last_aggro_at = started
    perc = None
    runtime = None
    self_hp_hist: deque[float] = deque(maxlen=AGGRO_WINDOW)
    last_target_drop_at = started
    phase = "idle"

    def add_step(name: str, **extra: Any) -> None:
        row = {"step": name, "t_ms": _ms(clock(), started), **extra}
        steps.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    def expired() -> bool:
        if session_s is None:
            return False
        return _ms(clock(), started) >= session_s * 1000.0

    def note_flow(expansion: float, mag: float) -> None:
        payload["flow_samples"].append(
            {
                "t_ms": _ms(clock(), started),
                "expansion": expansion,
                "flow_magnitude": mag,
            }
        )
        payload["_expansion"] = expansion
        payload["_flow_magnitude"] = mag

    def motion_fn(image: np.ndarray) -> float:
        nonlocal frame_id, prev_obs
        frame_id += 1
        t2 = time.perf_counter()
        obs = encoder.encode(_as_frame(image, frame_id, clock()), (), prev_obs, clock(), False)
        payload["encode_ms"].append((time.perf_counter() - t2) * 1000.0)
        prev_obs = obs
        nav = obs.navigation
        expansion = float(getattr(nav, "expansion", 0.0) or 0.0) if nav is not None else 0.0
        mag = flow_magnitude_midnear(encoder.last_flow, encoder.config.near_y0)
        note_flow(expansion, mag)
        return float(mag)

    from l2_brain.live.perception import PerceptionHub
    from l2_brain.live.runtime import LiveRuntime
    from l2_brain.live.skills.result import SkillStatus

    perc = PerceptionHub(parser, focus_probe=focus, frames=grabber, now_ns=clock, motion_fn=motion_fn)
    runtime = LiveRuntime(perc, backend=backend, clock=clock, sleeper=sleeper, log=payload)

    def play(name: str, **kwargs: object) -> Any:
        t0 = time.perf_counter()
        if name == "target_next":
            payload["target_next_attempts"] = int(payload["target_next_attempts"]) + 1
        if name == "loot_target":
            payload["loot_skill_runs"] = int(payload["loot_skill_runs"]) + 1
        result = runtime.run_skill(name, **kwargs)
        payload["act_ms"].append((time.perf_counter() - t0) * 1000.0)
        if result.reason in {"kill_switch", "focus_lost", "capture_lost"}:
            payload["aborted"] = result.reason
        return result

    def mark_aggro(parsed: HUDParseResult) -> None:
        hp = parsed.self_hp_ratio
        no_dmg = _ms(clock(), last_target_drop_at) / 1000.0
        needed = should_aggro_interrupt(
            self_hp=hp,
            prev_self_hps=list(self_hp_hist),
            target_locked=bool(payload.get("target_locked")),
            target_no_damage_s=no_dmg,
        )
        if hp is not None:
            self_hp_hist.append(float(hp))
        if (
            needed
            and phase != "loot"
            and _ms(clock(), last_aggro_at) >= AGGRO_COOLDOWN_S * 1000.0
        ):
            payload["_aggro_pending"] = True

    def sense() -> HUDParseResult | None:
        if expired():
            return None
        if not focus():
            payload["aborted"] = "focus_lost"
            return None
        t0 = time.perf_counter()
        state = runtime.observe()
        observe_ms = (time.perf_counter() - t0) * 1000.0
        payload["observe_ms"].append(observe_ms)
        parsed = perc.last_hud
        if perc.last_hud_parse_ms is not None:
            payload["parse_ms"].append(perc.last_hud_parse_ms)
        if parsed is not None and parsed.valid:
            bridge.publish(parsed, now_ns=clock())
        if not state.capture_ok:
            payload["aborted"] = "capture_lost"
            return None
        payload["ticks"] = int(payload["ticks"]) + 1
        if state.self_hp is not None:
            prev = payload.get("self_hp_min")
            payload["self_hp_end"] = float(state.self_hp)
            if prev is None or float(state.self_hp) < float(prev):
                payload["self_hp_min"] = float(state.self_hp)
        if state.self_hp is not None and state.self_hp < SELF_HP_ABORT:
            payload["aborted"] = "self_hp_low"
        elif parsed is not None:
            mark_aggro(parsed)
        return parsed

    def pause(seconds: float) -> bool:
        until = clock() + int(seconds * 1_000_000_000)
        while clock() < until:
            if expired() or payload.get("aborted"):
                return True
            sleeper(TICK_S)
            if sense() is None:
                return True
        return bool(payload.get("aborted") or expired())

    def wait_lock(seconds: float) -> tuple[bool, float | None]:
        until = clock() + int(seconds * 1_000_000_000)
        while clock() < until and not expired():
            sleeper(TICK_S)
            parsed = sense()
            if payload.get("aborted") or parsed is None:
                return False, None
            if runtime.state.target_locked is True and runtime.state.target_dead is not True:
                hp = runtime.state.target_hp
                if hp is not None and hp >= ENGAGE_HP_MIN:
                    return True, hp
        return False, None

    def tap_f2() -> bool:
        result = play("tap_hotkey", key="F2", slot=2)
        if result.status is not SkillStatus.SUCCESS:
            return False
        payload["f2_pulses"] = int(payload["f2_pulses"]) + 1
        add_step("F2", hid_sent=True, pulse=int(payload["f2_pulses"]))
        return True

    def tap_f1(cycle: int, *, phase_name: str, attempt: int | None = None) -> bool:
        result = play("target_next", wait=False)
        if result.status is not SkillStatus.SUCCESS:
            return False
        payload["f1_pulses"] = int(payload["f1_pulses"]) + 1
        extra = {"attempt": attempt} if attempt is not None else {}
        add_step("F1", hid_sent=True, cycle=cycle, phase=phase_name, **extra)
        return True

    def exec_aggro(cycle: int) -> tuple[bool, float | None]:
        nonlocal last_aggro_at, last_target_drop_at
        payload["_aggro_pending"] = False
        last_aggro_at = clock()
        escaped = play("close_dialog")
        if escaped.status is SkillStatus.ABORTED:
            return False, None
        add_step("Escape", hid_sent=True, cycle=cycle, reason="aggro")
        payload["target_locked"] = False
        if not tap_f1(cycle, phase_name="aggro"):
            return False, None
        locked, initial = wait_lock(SCAN_S)
        if payload.get("aborted"):
            return False, None
        if not locked:
            add_step("aggro_miss", cycle=cycle)
            return False, None
        payload["target_locked"] = True
        payload["aggro_interrupts"] = int(payload["aggro_interrupts"]) + 1
        payload["aggro_triggers"] = int(payload["aggro_interrupts"])
        add_step("aggro_lock", cycle=cycle, target_hp=initial, interrupt=payload["aggro_interrupts"])
        for _ in (1, 2):
            if not tap_f2():
                return False, None
            if pause(0.18) and payload.get("aborted"):
                return False, None
        last_target_drop_at = clock()
        return True, initial

    def exec_u_turn(cycle: int, roam_total: int) -> bool:
        add_step("u_turn", cycle=cycle, roam_cycles=roam_total)
        go_right = (roam_total - 1) % 2 == 0
        result = play("u_turn", go_right=go_right)
        if result.status is not SkillStatus.SUCCESS:
            return False
        payload["u_turns_executed"] = int(payload["u_turns_executed"]) + 1
        payload["u_turns"] = int(payload["u_turns_executed"])
        add_step("u_turn_done", cycle=cycle, u_turns=payload["u_turns_executed"])
        return True

    def take_pending_aggro(cycle: int) -> tuple[bool, float | None] | None:
        if not payload.get("_aggro_pending") or payload.get("aborted"):
            return None
        return exec_aggro(cycle)

    try:
        if not focus():
            payload["aborted"] = "focus_not_parallels"
            add_step("abort", reason="focus_not_parallels")
            return _finish_integrated(payload, out_path, clock, started, backend, encoder)
        grabber.start()
        add_step(
            "integrated_start",
            cap=kill_target,
            session_s=session_s,
            farm=False,
            walk_ms=WALK_MS,
            peel_ms=PEEL_MS,
            roam_fail_limit=ROAM_FAIL_LIMIT,
            self_hp_abort=SELF_HP_ABORT,
        )
        parsed = sense()
        settled_at = clock()
        while parsed is not None and _ms(clock(), settled_at) < SETTLE_S * 1000.0:
            sleeper(TICK_S)
            parsed = sense()
            if payload.get("aborted"):
                add_step("abort", reason=payload["aborted"])
                return _finish_integrated(payload, out_path, clock, started, backend, encoder)
        if parsed is None or expired():
            payload["aborted"] = payload.get("aborted") or "session_timeout"
            add_step("abort", reason=payload["aborted"])
            return _finish_integrated(payload, out_path, clock, started, backend, encoder)
        start_hp = parsed.self_hp_ratio
        payload["start_self_hp"] = start_hp
        payload["self_hp_start"] = start_hp
        if start_hp is not None:
            payload["self_hp_min"] = float(start_hp)
        if not parsed.valid or start_hp is None or start_hp <= SELF_HP_MIN:
            payload["aborted"] = "self_hp_low"
            add_step("abort", reason="self_hp_low", self_hp=start_hp)
            return _finish_integrated(payload, out_path, clock, started, backend, encoder)
        add_step("self_bars_ok", self_hp=start_hp)

        failed_search = 0
        roam_total = 0
        empty_since_kill = 0
        combat_secs: list[float] = []
        forced_hp: float | None = None
        search_started: int | None = None
        roam_before = 0

        while int(payload["kills_completed"]) < kill_target and not expired() and not payload.get("aborted"):
            cycle = int(payload["kills_completed"]) + 1
            if search_started is None:
                search_started = clock()
                roam_before = roam_total
            t_inf = time.perf_counter()
            payload["infer_ms"].append((time.perf_counter() - t_inf) * 1000.0)
            locked = False
            initial: float | None = None
            pre_engaged = False
            if forced_hp is not None:
                locked = True
                initial = forced_hp
                forced_hp = None
                pre_engaged = True
                payload["target_locked"] = True
                add_step("COMBAT", cycle=cycle, target_hp=initial, from_aggro=True)
            else:
                phase = "scan"
                add_step("SCAN", cycle=cycle)
                for attempt in range(1, SCAN_F1 + 1):
                    if not tap_f1(cycle, phase_name="SCAN", attempt=attempt):
                        add_step("abort", reason=payload.get("aborted"))
                        return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                    locked, initial = wait_lock(SCAN_S)
                    if payload.get("aborted"):
                        add_step("abort", reason=payload["aborted"])
                        return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                    grabbed = take_pending_aggro(cycle)
                    if grabbed is not None:
                        ok, hp = grabbed
                        if payload.get("aborted"):
                            add_step("abort", reason=payload["aborted"])
                            return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                        if ok:
                            locked = True
                            initial = hp
                            pre_engaged = True
                            failed_search = 0
                            empty_since_kill = 0
                            break
                    if locked:
                        payload["target_locked"] = True
                        add_step("locked", cycle=cycle, target_hp=initial, attempt=attempt)
                        failed_search = 0
                        empty_since_kill = 0
                        break
            search_ms = _ms(clock(), search_started)
            skip_fight = False
            if not locked:
                add_step("blind_engage", cycle=cycle)
                payload["attack_skill_runs"] = int(payload["attack_skill_runs"]) + 1
                engage_hp = runtime.state.self_hp
                lowest_hp = engage_hp

                def on_blind(result: Any) -> bool:
                    nonlocal lowest_hp
                    hp_now = runtime.state.self_hp
                    if hp_now is not None and (lowest_hp is None or float(hp_now) < float(lowest_hp)):
                        lowest_hp = float(hp_now)
                    return True

                fight = runtime.run_skill(
                    "attack_target",
                    engage_f2=True,
                    require_lock=False,
                    on_tick=on_blind,
                )
                payload["f2_pulses"] = int(payload["f2_pulses"]) + int(fight.data.get("f2_sent") or 0)
                if fight.reason in {"focus_lost", "capture_lost", "kill_switch"}:
                    payload["aborted"] = fight.reason
                    add_step("abort", reason=fight.reason)
                    return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                melee = (
                    int(fight.data.get("f2_sent") or 0) >= 1
                    and engage_hp is not None
                    and lowest_hp is not None
                    and float(engage_hp) - float(lowest_hp) >= ENGAGE_DAMAGE_EPS
                )
                if fight.status is SkillStatus.SUCCESS and fight.reason == "target_dead":
                    payload["attack_skill_success"] = int(payload["attack_skill_success"]) + 1
                    payload["target_locked"] = True
                    payload["target_killed"] = True
                    payload["entity_defeated"] = True
                    locked = True
                    initial = 0.0
                    skip_fight = True
                    failed_search = 0
                    empty_since_kill = 0
                    add_step("target_dead", cycle=cycle, target_hp=0.0, via="blind_engage")
                elif melee:
                    payload["attack_skill_success"] = int(payload["attack_skill_success"]) + 1
                    payload["target_locked"] = True
                    payload["target_killed"] = True
                    payload["entity_defeated"] = True
                    locked = True
                    initial = 0.0
                    skip_fight = True
                    failed_search = 0
                    empty_since_kill = 0
                    add_step(
                        "target_dead",
                        cycle=cycle,
                        target_hp=0.0,
                        via="blind_melee",
                        self_hp_from=engage_hp,
                        self_hp_to=lowest_hp,
                    )
                else:
                    payload["attack_skill_failed"] = int(payload["attack_skill_failed"]) + 1
                    if int(fight.data.get("f2_sent") or 0) >= 1:
                        add_step("LOOT", cycle=cycle, via="after_f2")
                        if pause(MULTI_LOOT_DROP_S) and payload.get("aborted"):
                            add_step("abort", reason=payload["aborted"])
                            return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                        looted = play("loot_target")
                        if looted.status is SkillStatus.ABORTED or looted.reason in {
                            "focus_lost",
                            "capture_lost",
                            "kill_switch",
                        }:
                            payload["aborted"] = payload.get("aborted") or looted.reason
                            add_step("abort", reason=payload["aborted"])
                            return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                        if looted.status is SkillStatus.SUCCESS:
                            payload["loot_pickup_sent"] = True
                            taps = int(looted.data.get("taps") or LOOT_TAPS)
                            payload["loot_actions_sent"] = int(payload["loot_actions_sent"]) + taps
                            for tap in range(1, taps + 1):
                                add_step("F3", hid_sent=True, cycle=cycle, tap=tap, via="after_f2")
                        if pause(LOOT_SETTLE_S) and payload.get("aborted"):
                            add_step("abort", reason=payload["aborted"])
                            return _finish_integrated(payload, out_path, clock, started, backend, encoder)
            if not locked:
                if empty_since_kill >= ROAM_FAIL_LIMIT:
                    payload["aborted"] = "roam_limit"
                    add_step("abort", reason="roam_limit", roam_cycles=roam_total)
                    return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                phase = "roam"
                add_step("ROAM_SEARCH", cycle=cycle, failed_search=failed_search + 1)
                direction = "right" if roam_total % 2 == 0 else "left"
                rotated = play("rotate_right" if direction == "right" else "rotate_left", duration_ms=ARROW_MS)
                if rotated.status is not SkillStatus.SUCCESS:
                    add_step("abort", reason=payload.get("aborted") or rotated.reason)
                    return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                add_step("arrow", hid_sent=True, key=f"{direction}_arrow", duration_ms=ARROW_MS, cycle=cycle)
                for step in range(1, ROAM_WALK_PULSES + 1):
                    walked = play("walk_pulse", duration_ms=WALK_MS)
                    if walked.status is not SkillStatus.SUCCESS:
                        add_step("abort", reason=payload.get("aborted") or walked.reason)
                        return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                    add_step("HoldKey", key="w", hid_sent=True, duration_ms=WALK_MS, cycle=cycle, pulse=step)
                    parsed = sense()
                    if payload.get("aborted"):
                        add_step("abort", reason=payload["aborted"])
                        return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                    grabbed = take_pending_aggro(cycle)
                    if grabbed is not None:
                        ok, hp = grabbed
                        if payload.get("aborted"):
                            add_step("abort", reason=payload["aborted"])
                            return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                        if ok:
                            forced_hp = hp
                            failed_search = 0
                            empty_since_kill = 0
                            break
                    if step < ROAM_WALK_PULSES and pause(WALK_GAP_S) and payload.get("aborted"):
                        add_step("abort", reason=payload["aborted"])
                        return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                    grabbed = take_pending_aggro(cycle)
                    if grabbed is not None:
                        ok, hp = grabbed
                        if payload.get("aborted"):
                            add_step("abort", reason=payload["aborted"])
                            return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                        if ok:
                            forced_hp = hp
                            failed_search = 0
                            empty_since_kill = 0
                            break
                if forced_hp is not None:
                    continue
                roam_total += 1
                failed_search += 1
                empty_since_kill += 1
                payload["roam_cycles"] = roam_total
                if failed_search >= ROAM_UTURN_AFTER:
                    if not exec_u_turn(cycle, roam_total):
                        add_step("abort", reason=payload.get("aborted"))
                        return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                    failed_search = 0
                    grabbed = take_pending_aggro(cycle)
                    if grabbed is not None:
                        ok, hp = grabbed
                        if payload.get("aborted"):
                            add_step("abort", reason=payload["aborted"])
                            return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                        if ok:
                            forced_hp = hp
                            empty_since_kill = 0
                            continue
                if empty_since_kill >= ROAM_FAIL_LIMIT:
                    payload["aborted"] = "roam_limit"
                    add_step("abort", reason="roam_limit", roam_cycles=roam_total)
                    return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                continue

            if skip_fight:
                killed = True
                combat_started = clock()
                add_step("COMBAT", cycle=cycle, target_hp=initial, via="blind_engage")
            else:
                phase = "combat"
                combat_started = clock()
                killed = False
            last_target_drop_at = combat_started
            if not skip_fight and pre_engaged and not any(
                row.get("step") == "COMBAT" and row.get("cycle") == cycle for row in steps[-8:]
            ):
                add_step("COMBAT", cycle=cycle, target_hp=initial, from_aggro=True)
            if not skip_fight and not pre_engaged:
                add_step("COMBAT", cycle=cycle, target_hp=initial)
            hub.clear()
            last_hp = initial
            burst = 0

            def on_combat(result: Any) -> bool:
                nonlocal last_hp, last_target_drop_at, last_l1_at, burst
                parsed = perc.last_hud
                if parsed is not None:
                    mark_aggro(parsed)
                hp = runtime.state.target_hp
                if last_hp is not None and hp is not None and last_hp - hp >= ENGAGE_DAMAGE_EPS:
                    last_target_drop_at = clock()
                    add_step("hp_delta", cycle=cycle, from_hp=last_hp, to_hp=hp)
                last_hp = hp if hp is not None else last_hp
                if result.reason == "l1_peel":
                    burst += 1
                    payload["l1_stuck_triggers"] = int(payload["l1_stuck_triggers"]) + 1
                    payload["l1_triggers"] = int(payload["l1_stuck_triggers"])
                    last_l1_at = clock()
                    add_step(
                        "l1_stuck",
                        cycle=cycle,
                        reason="static_no_damage",
                        expansion=payload.get("_expansion"),
                        flow_magnitude=payload.get("_flow_magnitude"),
                        trigger=payload["l1_triggers"],
                    )
                    add_step(
                        "l1_peel",
                        hid_sent=True,
                        key=result.data.get("key"),
                        duration_ms=PEEL_MS,
                        cycle=cycle,
                    )
                if payload.get("aborted") or payload.get("_aggro_pending"):
                    return False
                return True

            fight = None
            if not skip_fight:
                payload["attack_skill_runs"] = int(payload["attack_skill_runs"]) + 1
                fight = runtime.run_skill(
                    "attack_target",
                    engage_f2=not pre_engaged,
                    require_lock=True,
                    on_tick=on_combat,
                )
                payload["f2_pulses"] = int(payload["f2_pulses"]) + int(fight.data.get("f2_sent") or 0)
                if fight.status is SkillStatus.SUCCESS and fight.reason == "target_dead":
                    payload["attack_skill_success"] = int(payload["attack_skill_success"]) + 1
                elif fight.status is SkillStatus.FAILED:
                    payload["attack_skill_failed"] = int(payload["attack_skill_failed"]) + 1
                if payload.get("_aggro_pending") and runtime.active_skill is not None:
                    runtime.cancel_skill("aggro")
                if payload.get("aborted"):
                    add_step("abort", reason=payload["aborted"])
                    return _finish_integrated(payload, out_path, clock, started, backend, encoder)
            grabbed = take_pending_aggro(cycle)
            if grabbed is not None:
                ok, hp = grabbed
                if payload.get("aborted"):
                    add_step("abort", reason=payload["aborted"])
                    return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                if ok:
                    if sense() is None and payload.get("aborted"):
                        add_step("abort", reason=payload["aborted"])
                        return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                    dead_now = runtime.state.target_dead is True or (
                        runtime.state.target_hp is not None and runtime.state.target_hp <= 0.0
                    )
                    if dead_now:
                        killed = True
                        payload["target_killed"] = True
                        payload["entity_defeated"] = True
                        last_hp = 0.0
                        add_step(
                            "target_dead",
                            cycle=cycle,
                            target_hp=0.0,
                            time_to_kill_ms=_ms(clock(), combat_started),
                            from_aggro=True,
                        )
                    else:
                        forced_hp = hp
                        failed_search = 0
                        empty_since_kill = 0
                        continue
                else:
                    payload["target_locked"] = False
                    continue
            elif fight is not None and fight.status is SkillStatus.SUCCESS and fight.reason == "target_dead":
                killed = True
                payload["target_killed"] = True
                payload["entity_defeated"] = True
                add_step(
                    "target_dead",
                    cycle=cycle,
                    target_hp=runtime.state.target_hp,
                    time_to_kill_ms=_ms(clock(), combat_started),
                )
            elif runtime.state.target_dead is True or (
                runtime.state.target_hp is not None and runtime.state.target_hp <= 0.0
            ):
                killed = True
                payload["target_killed"] = True
                payload["entity_defeated"] = True
                add_step(
                    "target_dead",
                    cycle=cycle,
                    target_hp=runtime.state.target_hp,
                    time_to_kill_ms=_ms(clock(), combat_started),
                )
            combat_ms = _ms(clock(), combat_started)
            if not killed:
                add_step("combat_timeout", cycle=cycle, target_hp=last_hp)
                escaped = play("close_dialog")
                if escaped.status is SkillStatus.ABORTED:
                    add_step("abort", reason=payload.get("aborted") or escaped.reason)
                    return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                add_step("Escape", hid_sent=True, cycle=cycle, reason="combat_timeout")
                payload["target_locked"] = False
                if pause(MULTI_RESET_S) and payload.get("aborted"):
                    add_step("abort", reason=payload["aborted"])
                    return _finish_integrated(payload, out_path, clock, started, backend, encoder)
                continue

            phase = "loot"
            loot_started = clock()
            add_step("LOOT", cycle=cycle)
            if pause(MULTI_LOOT_DROP_S) and payload.get("aborted"):
                add_step("abort", reason=payload["aborted"])
                return _finish_integrated(payload, out_path, clock, started, backend, encoder)
            looted = play("loot_target")
            if looted.status is not SkillStatus.SUCCESS:
                add_step("abort", reason=payload.get("aborted") or looted.reason)
                return _finish_integrated(payload, out_path, clock, started, backend, encoder)
            payload["loot_pickup_sent"] = True
            taps = int(looted.data.get("taps") or LOOT_TAPS)
            payload["loot_actions_sent"] = int(payload["loot_actions_sent"]) + taps
            for tap in range(1, taps + 1):
                add_step("F3", hid_sent=True, cycle=cycle, tap=tap)
            if pause(LOOT_SETTLE_S) and payload.get("aborted"):
                add_step("abort", reason=payload["aborted"])
                return _finish_integrated(payload, out_path, clock, started, backend, encoder)
            escaped = play("close_dialog")
            if escaped.status is SkillStatus.ABORTED:
                add_step("abort", reason=payload.get("aborted") or escaped.reason)
                return _finish_integrated(payload, out_path, clock, started, backend, encoder)
            payload["target_locked"] = False
            payload["kills_completed"] = int(payload["kills_completed"]) + 1
            payload["total_kills"] = payload["kills_completed"]
            combat_secs.append(combat_ms / 1000.0)
            payload["frags"].append(
                {
                    "kill": payload["kills_completed"],
                    "search_ms": search_ms,
                    "combat_ms": combat_ms,
                    "loot_ms": _ms(clock(), loot_started),
                    "roam_cycles": roam_total - roam_before,
                    "l1_triggers": burst,
                    "initial_hp": initial,
                    "final_hp": 0.0,
                }
            )
            add_step("frag", cycle=cycle, kills_completed=payload["kills_completed"], combat_ms=combat_ms)
            search_started = None
            empty_since_kill = 0
            if payload["kills_completed"] >= kill_target:
                break
            if pause(MULTI_RESET_S) and payload.get("aborted"):
                add_step("abort", reason=payload["aborted"])
                return _finish_integrated(payload, out_path, clock, started, backend, encoder)

        if payload.get("aborted"):
            add_step("abort", reason=payload["aborted"])
            return _finish_integrated(payload, out_path, clock, started, backend, encoder)
        if payload["kills_completed"] >= kill_target:
            payload["ok"] = True
            add_step(
                "SUCCESS",
                kills_completed=payload["kills_completed"],
                roam_cycles=roam_total,
                farm=False,
                aggro_interrupts=payload["aggro_interrupts"],
                l1_triggers=payload["l1_triggers"],
                u_turns_executed=payload["u_turns_executed"],
            )
        else:
            payload["aborted"] = "session_timeout"
            add_step("abort", reason="session_timeout", kills_completed=payload["kills_completed"])
        if combat_secs:
            payload["avg_combat_duration_sec"] = float(sum(combat_secs) / len(combat_secs))
        return _finish_integrated(payload, out_path, clock, started, backend, encoder)
    except Exception as exc:  # noqa: BLE001 — always release HID and write a report
        payload["aborted"] = payload.get("aborted") or f"error:{type(exc).__name__}"
        add_step("abort", reason=payload["aborted"], error=str(exc)[:200])
        return _finish_integrated(payload, out_path, clock, started, backend, encoder)
    finally:
        if runtime is not None:
            runtime.shutdown()
        if own_grabber:
            grabber.close()


def _finish_integrated(
    payload: dict[str, Any],
    out_path: Path | None,
    clock: Callable[[], int],
    started: int,
    backend: CGEventInputBackend | None,
    encoder: NavigationEncoder | None,
) -> dict[str, Any]:
    from l2_brain.live.s4_probe import _finish

    if encoder is not None:
        encoder.close()
    payload["total_kills"] = int(payload.get("kills_completed") or 0)
    payload["l1_triggers"] = int(payload.get("l1_triggers") or payload.get("l1_stuck_triggers") or 0)
    payload["observe"] = summarize(list(payload.pop("observe_ms", [])))
    payload["parse"] = summarize(list(payload.pop("parse_ms", [])))
    payload["encode"] = summarize(list(payload.pop("encode_ms", [])))
    payload["infer"] = summarize(list(payload.pop("infer_ms", [])))
    payload["act"] = summarize(list(payload.pop("act_ms", [])))
    e2e = [
        float(payload["observe"]["p95"])
        + float(payload["parse"]["p95"])
        + float(payload["encode"]["p95"])
        + float(payload["infer"]["p95"])
        + float(payload["act"]["p95"])
    ]
    payload["e2e_p95_ms"] = e2e[0]
    payload.pop("_expansion", None)
    payload.pop("_flow_magnitude", None)
    payload.pop("_aggro_pending", None)
    finished = _finish(payload, out_path, clock, started, backend)
    finished["elapsed_time_sec"] = float(finished.get("session_ms") or 0.0) / 1000.0
    finished["elapsed_sec"] = float(finished["elapsed_time_sec"])
    finished["total_time_sec"] = float(finished["elapsed_time_sec"])
    finished["avg_combat_sec"] = finished.get("avg_combat_duration_sec")
    finished["u_turns"] = int(finished.get("u_turns_executed") or 0)
    finished["aggro_triggers"] = int(finished.get("aggro_interrupts") or 0)
    finished["stuck_keys"] = int(finished.get("stuck_keys_count") or 0)
    finished["target_next_attempts"] = int(finished.get("target_next_attempts") or finished.get("f1_pulses") or 0)
    if backend is not None:
        finished["f2_input_count"] = sum(
            1 for row in backend.log if row.action_type == "SkillActivate" and row.key == "F2"
        )
        finished["release_all_called"] = any(row.reason == "release_all" for row in backend.log)
    if finished.get("runtime_validation"):
        from l2_brain.live.runtime_validation import combat_validation_result

        finished["validation_result"] = combat_validation_result(finished)
        if finished["validation_result"] == "PASS":
            finished["ok"] = True
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(finished, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return finished
