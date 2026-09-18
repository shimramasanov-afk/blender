"""S4 combat probe. Hod 80 roam series is 5 kills, pulsed w. No farm."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from l2_brain.capture.errors import CaptureError
from l2_brain.experiment.clocks import mono_ns
from l2_brain.io.actions import (
    EmergencyStop,
    HoldKey,
    SkillActivate,
    TargetMethod,
    TargetSelect,
)
from l2_brain.io.cgevent_backend import CGEventInputBackend
from l2_brain.io.focus import frontmost_app, is_allowed_frontmost
from l2_brain.io.profile import GameInputProfile
from l2_brain.telemetry.events import EntityDefeated, TargetState
from l2_brain.telemetry.hub import TelemetryHub
from l2_brain.telemetry.vision_bridge import VisionTelemetryBridge
from l2_brain.vision.hud_parser import HUDParseResult, HUDParser

MAX_SESSION_S = 15.0
MAX_TICKS = 300
CLEAN_SESSION_S = 12.0
CLEAN_MAX_TICKS = 360
TICK_S = 0.05
SETTLE_S = 1.0
LOCK_TIMEOUT_S = 3.0
CLEAR_TIMEOUT_S = 1.0
DAMAGE_WATCH_S = 4.0
CLEAN_DAMAGE_WATCH_S = 8.0
SELF_HP_MIN = 0.8
DAMAGE_EPS = 0.02
CLEAN_DAMAGE_EPS = 0.05
CLEAN_HP_MIN = 0.85
ENGAGE_HP_MIN = 0.15
ENGAGE_LOCK_TIMEOUT_S = 2.0
ENGAGE_DAMAGE_EPS = 0.04
ENGAGE_F2_GAP_S = 0.18
F2_GAP_S = 0.20
DEFAULT_PROFILE = Path("config/window_profiles/parallels_l2.json")
DEFAULT_OUT = Path("docs/evidence/live-s4/first-combat-probe.json")
CLEAN_OUT = Path("docs/evidence/live-s4/second-combat-probe.json")
ENGAGE_OUT = Path("docs/evidence/live-s4/combat-damage-probe.json")
KILL_OUT = Path("docs/evidence/live-s4/kill-loot-probe.json")
MULTI_OUT = Path("docs/evidence/live-s4/multi-kill-probe.json")
LOOT_DROP_S = 0.30
LOOT_SETTLE_S = 0.50
MULTI_KILL_CAP = 3
MULTI_SESSION_S = 45.0
MULTI_MAX_TICKS = 900
MULTI_SCAN_S = 2.5
MULTI_COMBAT_S = 12.0
MULTI_F1_ATTEMPTS = 3
MULTI_LOOT_DROP_S = 0.35
MULTI_RESET_S = 0.50
MULTI_ARROW_MS = 400
SEARCH_OUT = Path("docs/evidence/live-s4/keyboard-search-probe.json")
SEARCH_SESSION_S = 30.0
SEARCH_MAX_TICKS = 600
SEARCH_F1_ATTEMPTS = 1
SEARCH_MAX_STEPS = 3
SEARCH_SCAN_S = 1.5
SEARCH_POST_S = 1.5
SEARCH_ARROW_MS = 450
SEARCH_WALK_MS = 500
SEARCH_HOLD_MAX_MS = 500
SEARCH_SETTLE_S = 0.30
ROAM_OUT = Path("docs/evidence/live-s4/spot-roam-series-5.json")
ROAM_KILL_CAP = 5
ROAM_SESSION_S = 180.0
ROAM_MAX_TICKS = 4000
ROAM_SCAN_F1 = 2
ROAM_SCAN_S = 1.2
ROAM_FAIL_LIMIT = 10
ROAM_WALK_PULSES = 3
ROAM_WALK_MS = 500
ROAM_WALK_GAP_S = 0.05
ROAM_ARROW_MS = 450
ROAM_LOOT_TAPS = 3
ROAM_LOOT_GAP_S = 0.35
ROAM_LOOT_SETTLE_S = 0.40
ROAM_COMBAT_NO_DAMAGE_S = 8.0
ROAM_COMBAT_MAX_S = 25.0
ROAM_SELF_HP_MIN = 0.30
ROAM_SELF_HP_ABORT = 0.15
ROAM_VANISH_HP = 0.08
HOTBAR = {"F1": "/targetnext", "F2": "Attack", "F3": "Pickup"}
assert ROAM_WALK_MS <= 800
assert ROAM_WALK_MS <= SEARCH_HOLD_MAX_MS
assert ROAM_ARROW_MS <= SEARCH_HOLD_MAX_MS


class FrameGrabber(Protocol):
    def start(self) -> None: ...

    def latest_image(self) -> np.ndarray: ...

    def close(self) -> None: ...


@dataclass
class ScriptedGrabber:
    """Test double. One image per call; last frame repeats."""

    frames: list[np.ndarray]
    index: int = 0

    def start(self) -> None:
        return None

    def latest_image(self) -> np.ndarray:
        if not self.frames:
            raise RuntimeError("no scripted frames")
        image = self.frames[min(self.index, len(self.frames) - 1)]
        if self.index < len(self.frames) - 1:
            self.index += 1
        return image

    def latest_shot(self) -> tuple[np.ndarray, int]:
        image = np.ascontiguousarray(self.latest_image()).copy()
        ts = int(getattr(self, "_ts_ns", 1_000_000_000))
        self._ts_ns = ts + 33_000_000
        return image, ts

    def close(self) -> None:
        return None


@dataclass
class SCKGrabber:
    """Unmasked SCK stream. HUD masks would blacken the bars."""

    window_id: int
    fps: int = 30
    latest_timeout_s: float = 4.0
    source: Any = field(default=None, init=False)

    def start(self) -> None:
        from l2_brain.capture.helper import resolve_helper
        from l2_brain.capture.sck import SCKConfig, SCKFrameSource

        helper = resolve_helper(build=True)
        self.source = SCKFrameSource(
            SCKConfig(
                helper_path=helper,
                window_id=self.window_id,
                fps=self.fps,
                profile_path=None,
                latest_timeout_s=self.latest_timeout_s,
            )
        )
        self.source.initialize()
        self.source.latest()

    def latest_image(self) -> np.ndarray:
        if self.source is None:
            raise RuntimeError("SCKGrabber is closed")
        frame = self.source.latest()
        if frame.image is None:
            raise RuntimeError("empty frame")
        return np.ascontiguousarray(frame.image)

    def latest_shot(self) -> tuple[np.ndarray, int]:
        if self.source is None:
            raise RuntimeError("SCKGrabber is closed")
        frame = self.source.latest()
        if frame.image is None:
            raise RuntimeError("empty frame")
        image = np.ascontiguousarray(frame.image).copy()
        return image, int(frame.timestamp_capture_ns)

    def close(self) -> None:
        if self.source is not None:
            self.source.close()
            self.source = None


def s4_input_profile() -> GameInputProfile:
    return GameInputProfile(
        name="s4_interlude_v0",
        target_window="parallels-desktop",
        next_target_key="F1",
        attack_key="F2",
        kill_switch="F12",
        watchdog_timeout_ms=250,
    )


def run_s4_probe(
    *,
    live: bool,
    danger_confirmed: bool,
    window_id: int | None = None,
    target_pid: int | None = None,
    profile_path: Path = DEFAULT_PROFILE,
    out_path: Path | None = DEFAULT_OUT,
    grabber: FrameGrabber | None = None,
    backend: CGEventInputBackend | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    now_ns: Callable[[], int] | None = None,
    focus_probe: Callable[[], bool] | None = None,
    clean_target: bool = False,
    engage_any: bool = False,
    kill_and_loot: bool = False,
    multi_kill: int = 0,
    verify_search: bool = False,
    spot_series: bool = False,
    spot_kills: int = ROAM_KILL_CAP,
    spot_timeout_s: float = ROAM_SESSION_S,
    no_heal: bool = True,
) -> dict[str, Any]:
    clock = now_ns or mono_ns
    started = clock()
    kill_target = min(max(int(multi_kill or 0), 0), MULTI_KILL_CAP)
    if spot_series:
        session_s = min(max(float(spot_timeout_s), 1.0), ROAM_SESSION_S)
        max_ticks = ROAM_MAX_TICKS
        watch_s = ROAM_COMBAT_MAX_S
        kill_target = min(max(int(spot_kills), 1), ROAM_KILL_CAP)
    elif verify_search:
        session_s = SEARCH_SESSION_S
        max_ticks = SEARCH_MAX_TICKS
        watch_s = MULTI_COMBAT_S
        kill_target = 0
    elif kill_target > 0:
        session_s = MULTI_SESSION_S
        max_ticks = MULTI_MAX_TICKS
        watch_s = MULTI_COMBAT_S
    else:
        long_session = clean_target or engage_any or kill_and_loot
        session_s = CLEAN_SESSION_S if long_session else MAX_SESSION_S
        max_ticks = CLEAN_MAX_TICKS if long_session else MAX_TICKS
        watch_s = CLEAN_DAMAGE_WATCH_S if long_session else DAMAGE_WATCH_S
    if engage_any or kill_and_loot:
        damage_eps = ENGAGE_DAMAGE_EPS
        lock_timeout_s = ENGAGE_LOCK_TIMEOUT_S
        f2_gap_s = ENGAGE_F2_GAP_S
    elif clean_target:
        damage_eps = CLEAN_DAMAGE_EPS
        lock_timeout_s = LOCK_TIMEOUT_S
        f2_gap_s = F2_GAP_S
    else:
        damage_eps = DAMAGE_EPS
        lock_timeout_s = LOCK_TIMEOUT_S
        f2_gap_s = F2_GAP_S
    steps: list[dict[str, Any]] = []
    payload: dict[str, Any] = {
        "ok": False,
        "s4_open": True,
        "clean_target": clean_target,
        "engage_any": engage_any,
        "kill_and_loot": kill_and_loot,
        "verify_search": verify_search,
        "spot_series": bool(spot_series),
        "no_heal": bool(no_heal or spot_series),
        "heal_sent": False,
        "total_kills": 0,
        "roam_cycles": 0,
        "avg_combat_duration_sec": None,
        "elapsed_time_sec": 0.0,
        "frags": [],
        "search_maneuver_executed": False,
        "search_maneuver_triggered": False,
        "rotation_type": "keyboard_arrow" if verify_search else None,
        "rotation_sent": False,
        "walk_step_sent": False,
        "target_acquired_after_search": False,
        "multi_kill": kill_target,
        "kills_completed": 0,
        "loot_actions_sent": 0,
        "total_session_ms": 0.0,
        "cycles": [],
        "target_killed": False,
        "loot_pickup_sent": False,
        "time_to_kill_ms": None,
        "entity_defeated": False,
        "hotbar": dict(HOTBAR),
        "live": bool(live and danger_confirmed),
        "hid_sent": False,
        "aborted": None,
        "window_id": window_id,
        "target_pid": target_pid,
        "start_self_hp": None,
        "target_name_detected": False,
        "target_locked": False,
        "initial_target_hp": None,
        "final_target_hp": None,
        "damage_detected": False,
        "f1_to_lock_ms": None,
        "f2_to_hp_drop_ms": None,
        "f1_pulses": 0,
        "f2_pulses": 0,
        "stuck_keys_count": 0,
        "watchdog_tripped": False,
        "ticks": 0,
        "session_ms": 0.0,
        "steps": steps,
        "events": [],
        "transfer_claim": False,
        "farm": False,
        "walk": False,
    }
    if not live or not danger_confirmed:
        payload["aborted"] = "live_flags_required"
        return _finish(payload, out_path, clock, started, None)
    if grabber is None and (window_id is None or int(window_id) < 1):
        payload["aborted"] = "window_id_required"
        return _finish(payload, out_path, clock, started, None)

    parser = HUDParser.from_profile(profile_path)
    hub = TelemetryHub(maxlen=128)
    bridge = VisionTelemetryBridge(hub)
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
            return _finish(payload, out_path, clock, started, None)
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

    def add_step(name: str, **extra: Any) -> None:
        row = {"step": name, "t_ms": _ms(clock(), started), **extra}
        steps.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    try:
        if not focus():
            payload["aborted"] = "focus_not_parallels"
            add_step("abort", reason="focus_not_parallels")
            return _finish(payload, out_path, clock, started, backend)
        grabber.start()
        add_step("capture_start", fps=30)

        ticks = 0

        def expired() -> bool:
            return _ms(clock(), started) >= session_s * 1000.0 or ticks >= max_ticks

        def snapshot() -> HUDParseResult | None:
            nonlocal ticks
            if expired():
                return None
            if not focus():
                payload["aborted"] = "focus_lost"
                return None
            backend.pump()
            if backend.watchdog.active_holds and backend.watchdog.check(clock()):
                payload["watchdog_tripped"] = True
            try:
                image = grabber.latest_image()
            except (CaptureError, RuntimeError):
                payload["aborted"] = "capture_lost"
                return None
            parsed = parser.parse(image)
            if parsed.valid:
                bridge.publish(parsed, now_ns=clock())
            ticks += 1
            payload["ticks"] = ticks
            return parsed

        settled_at = clock()
        parsed = snapshot()
        while parsed is not None and _ms(clock(), settled_at) < SETTLE_S * 1000.0:
            sleeper(TICK_S)
            parsed = snapshot()
            if payload.get("aborted"):
                add_step("abort", reason=payload["aborted"])
                return _finish(payload, out_path, clock, started, backend)
        if parsed is None or expired():
            payload["aborted"] = payload.get("aborted") or "session_timeout"
            add_step("abort", reason=payload["aborted"])
            return _finish(payload, out_path, clock, started, backend)
        start_hp = parsed.self_hp_ratio
        payload["start_self_hp"] = start_hp
        hp_floor = ROAM_SELF_HP_MIN if spot_series else SELF_HP_MIN
        if not parsed.valid or start_hp is None or start_hp <= hp_floor:
            payload["aborted"] = "self_hp_low"
            add_step("abort", reason="self_hp_low", self_hp=start_hp, valid=parsed.valid)
            return _finish(payload, out_path, clock, started, backend)
        add_step("self_bars_ok", self_hp=start_hp)

        if spot_series:
            return _run_spot_series(
                payload=payload,
                backend=backend,
                hub=hub,
                clock=clock,
                started=started,
                sleeper=sleeper,
                snapshot=snapshot,
                expired=expired,
                add_step=add_step,
                out_path=out_path,
                focus=focus,
                kill_target=kill_target,
            )

        if verify_search:
            return _run_verify_search(
                payload=payload,
                backend=backend,
                hub=hub,
                clock=clock,
                started=started,
                sleeper=sleeper,
                snapshot=snapshot,
                expired=expired,
                add_step=add_step,
                out_path=out_path,
                focus=focus,
            )

        if kill_target > 0:
            return _run_multi_kill(
                payload=payload,
                backend=backend,
                hub=hub,
                clock=clock,
                started=started,
                sleeper=sleeper,
                snapshot=snapshot,
                expired=expired,
                add_step=add_step,
                out_path=out_path,
                kill_target=kill_target,
            )

        if clean_target:
            ev = _tap_escape(backend, payload)
            if ev is None:
                add_step("abort", reason=payload["aborted"])
                return _finish(payload, out_path, clock, started, backend)
            add_step("pre_clear_Escape", hid_sent=ev.hid_sent, pulse=1)
            cleared = False
            last_clear: HUDParseResult | None = parsed
            for pulse in (1, 2):
                if pulse == 2:
                    ev = _tap_escape(backend, payload)
                    if ev is None:
                        add_step("abort", reason=payload["aborted"])
                        return _finish(payload, out_path, clock, started, backend)
                    add_step("pre_clear_Escape", hid_sent=ev.hid_sent, pulse=2)
                clear_deadline = clock() + int(CLEAR_TIMEOUT_S * 1_000_000_000)
                while clock() < clear_deadline and not expired():
                    sleeper(TICK_S)
                    parsed = snapshot()
                    last_clear = parsed
                    if payload.get("aborted"):
                        add_step("abort", reason=payload["aborted"])
                        return _finish(payload, out_path, clock, started, backend)
                    if parsed is None:
                        break
                    if not _alive_target(parsed):
                        cleared = True
                        add_step(
                            "cleared",
                            target_locked=parsed.target_locked,
                            target_dead=parsed.target_dead,
                            target_hp=parsed.target_hp_ratio,
                        )
                        break
                if cleared:
                    break
            if not cleared:
                payload["aborted"] = "clear_timeout"
                extra = {}
                if last_clear is not None:
                    extra = {
                        "target_locked": last_clear.target_locked,
                        "target_dead": last_clear.target_dead,
                        "target_hp": last_clear.target_hp_ratio,
                    }
                add_step("abort", reason="clear_timeout", **extra)
                return _finish(payload, out_path, clock, started, backend)

        f1_at = clock()
        last_f1 = f1_at
        f1_pulses = 1
        ev = _send(backend, TargetSelect(method=TargetMethod.NEXT_HOTKEY), payload)
        if ev is None:
            add_step("abort", reason=payload["aborted"])
            return _finish(payload, out_path, clock, started, backend)
        add_step("F1", hid_sent=ev.hid_sent, pulse=1)
        payload["f1_pulses"] = 1

        locked_at: int | None = None
        saw_lock = False
        last_lock_hp: float | None = None
        lock_deadline = clock() + int(lock_timeout_s * 1_000_000_000)
        while clock() < lock_deadline and not expired():
            sleeper(TICK_S)
            parsed = snapshot()
            if payload.get("aborted"):
                add_step("abort", reason=payload["aborted"])
                return _finish(payload, out_path, clock, started, backend)
            if parsed is None:
                break
            target = hub.get_latest(TargetState)
            if parsed.target_locked and target is not None and target.locked:
                saw_lock = True
                hp = parsed.target_hp_ratio
                last_lock_hp = hp
                if (engage_any or kill_and_loot) and (
                    hp is None or hp < ENGAGE_HP_MIN or parsed.target_dead
                ):
                    continue
                if clean_target and (hp is None or hp <= CLEAN_HP_MIN):
                    if f1_pulses < 3 and _ms(clock(), last_f1) >= 350.0:
                        ev = _send(backend, TargetSelect(method=TargetMethod.NEXT_HOTKEY), payload)
                        if ev is None:
                            add_step("abort", reason=payload["aborted"])
                            return _finish(payload, out_path, clock, started, backend)
                        f1_pulses += 1
                        last_f1 = clock()
                        payload["f1_pulses"] = f1_pulses
                        add_step("F1", hid_sent=ev.hid_sent, pulse=f1_pulses, rejected_hp=hp)
                    continue
                locked_at = clock()
                payload["target_locked"] = True
                payload["target_name_detected"] = True
                payload["initial_target_hp"] = hp
                payload["f1_to_lock_ms"] = _ms(locked_at, f1_at)
                add_step(
                    "target_lock",
                    target_hp=hp,
                    f1_to_lock_ms=payload["f1_to_lock_ms"],
                    f1_pulses=f1_pulses,
                )
                break
        if locked_at is None:
            if clean_target and saw_lock:
                payload["aborted"] = "clean_hp_low"
            elif (engage_any or kill_and_loot) and saw_lock:
                payload["aborted"] = "engage_hp_low"
            else:
                payload["aborted"] = "lock_timeout"
            add_step("abort", reason=payload["aborted"], target_hp=last_lock_hp, f1_pulses=f1_pulses)
            return _finish(payload, out_path, clock, started, backend)

        f2_at = clock()
        ev = _send(backend, SkillActivate(slot=2, key="F2", duration_ms=40), payload)
        if ev is None:
            add_step("abort", reason=payload["aborted"])
            return _finish(payload, out_path, clock, started, backend)
        payload["f2_pulses"] = 1
        add_step("F2", pulse=1, hid_sent=ev.hid_sent)
        if clean_target or engage_any or kill_and_loot:
            gap_until = clock() + int(f2_gap_s * 1_000_000_000)
            while clock() < gap_until and not expired():
                sleeper(TICK_S)
                parsed = snapshot()
                if payload.get("aborted"):
                    add_step("abort", reason=payload["aborted"])
                    return _finish(payload, out_path, clock, started, backend)
                if parsed is None:
                    break
            ev = _send(backend, SkillActivate(slot=2, key="F2", duration_ms=40), payload)
            if ev is None:
                add_step("abort", reason=payload["aborted"])
                return _finish(payload, out_path, clock, started, backend)
            payload["f2_pulses"] = 2
            add_step("F2", pulse=2, hid_sent=ev.hid_sent)

        drop_at: int | None = None
        initial = payload["initial_target_hp"]
        watch_deadline = clock() + int(watch_s * 1_000_000_000)
        last_hp = initial
        while clock() < watch_deadline and not expired():
            sleeper(TICK_S)
            parsed = snapshot()
            if payload.get("aborted"):
                add_step("abort", reason=payload["aborted"])
                return _finish(payload, out_path, clock, started, backend)
            if parsed is None:
                break
            if parsed.target_locked:
                last_hp = parsed.target_hp_ratio
            dead = bool(parsed.target_dead or (last_hp is not None and last_hp <= 0.0))
            dropped = (
                initial is not None
                and last_hp is not None
                and (initial - last_hp) >= damage_eps
            )
            defeated = hub.get_latest(EntityDefeated) is not None
            if dropped and payload["f2_to_hp_drop_ms"] is None:
                drop_at = clock()
                payload["f2_to_hp_drop_ms"] = _ms(drop_at, f2_at)
                payload["damage_detected"] = True
                add_step(
                    "hp_delta",
                    initial_target_hp=initial,
                    final_target_hp=last_hp,
                    damage_detected=True,
                    f2_to_hp_drop_ms=payload["f2_to_hp_drop_ms"],
                )
            if dead or defeated:
                if dead and last_hp is None:
                    last_hp = 0.0
                payload["target_killed"] = True
                payload["entity_defeated"] = bool(defeated or dead)
                payload["time_to_kill_ms"] = _ms(clock(), f2_at)
                payload["damage_detected"] = True
                add_step(
                    "target_dead",
                    final_target_hp=last_hp,
                    time_to_kill_ms=payload["time_to_kill_ms"],
                    entity_defeated=payload["entity_defeated"],
                )
                break
            if not kill_and_loot and (dropped or dead):
                if dead and last_hp is None:
                    last_hp = 0.0
                payload["damage_detected"] = True
                break
        payload["final_target_hp"] = last_hp
        payload["initial_hp"] = initial
        payload["final_hp"] = last_hp
        payload["damage_detected"] = bool(
            payload["damage_detected"]
            or (
                initial is not None
                and last_hp is not None
                and (initial - last_hp) >= damage_eps
            )
            or (last_hp is not None and last_hp <= 0.0)
        )
        if not any(row.get("step") == "hp_delta" for row in steps):
            add_step(
                "hp_delta",
                initial_target_hp=initial,
                final_target_hp=last_hp,
                damage_detected=payload["damage_detected"],
                f2_to_hp_drop_ms=payload["f2_to_hp_drop_ms"],
            )

        if kill_and_loot and not payload["target_killed"]:
            payload["aborted"] = "kill_timeout"
            add_step("abort", reason="kill_timeout", final_target_hp=last_hp)
            ev = _tap_escape(backend, payload)
            if ev is not None:
                add_step("Escape", hid_sent=ev.hid_sent)
            return _finish(payload, out_path, clock, started, backend)

        if kill_and_loot:
            pause_until = clock() + int(LOOT_DROP_S * 1_000_000_000)
            while clock() < pause_until and not expired():
                sleeper(TICK_S)
                parsed = snapshot()
                if payload.get("aborted"):
                    add_step("abort", reason=payload["aborted"])
                    return _finish(payload, out_path, clock, started, backend)
            ev = _send(backend, SkillActivate(slot=3, key="F3", duration_ms=40), payload)
            if ev is None:
                add_step("abort", reason=payload["aborted"])
                return _finish(payload, out_path, clock, started, backend)
            payload["loot_pickup_sent"] = True
            add_step("F3", hid_sent=ev.hid_sent)
            settle_until = clock() + int(LOOT_SETTLE_S * 1_000_000_000)
            while clock() < settle_until and not expired():
                sleeper(TICK_S)
                parsed = snapshot()
                if payload.get("aborted"):
                    add_step("abort", reason=payload["aborted"])
                    return _finish(payload, out_path, clock, started, backend)

        ev = _tap_escape(backend, payload)
        if ev is None:
            add_step("abort", reason=payload["aborted"])
            return _finish(payload, out_path, clock, started, backend)
        add_step("Escape", hid_sent=ev.hid_sent)
        payload["ok"] = True
        add_step("done")
        return _finish(payload, out_path, clock, started, backend)
    except Exception as exc:  # noqa: BLE001 — always release HID and write a report
        payload["aborted"] = payload.get("aborted") or f"error:{type(exc).__name__}"
        add_step("abort", reason=payload["aborted"], error=str(exc)[:200])
        return _finish(payload, out_path, clock, started, backend)
    finally:
        if own_grabber:
            grabber.close()


def _run_verify_search(
    *,
    payload: dict[str, Any],
    backend: CGEventInputBackend,
    hub: TelemetryHub,
    clock: Callable[[], int],
    started: int,
    sleeper: Callable[[float], None],
    snapshot: Callable[[], HUDParseResult | None],
    expired: Callable[[], bool],
    add_step: Callable[..., None],
    out_path: Path | None,
    focus: Callable[[], bool],
) -> dict[str, Any]:
    """One empty-radius maneuver, then one kill. Not a wander loop."""

    def abort_now() -> dict[str, Any]:
        add_step("abort", reason=payload.get("aborted"))
        return _finish(payload, out_path, clock, started, backend)

    def pause(seconds: float) -> bool:
        until = clock() + int(seconds * 1_000_000_000)
        while clock() < until:
            if expired() or payload.get("aborted"):
                return True
            sleeper(TICK_S)
            if snapshot() is None:
                return True
        return bool(payload.get("aborted") or expired())

    def wait_lock(seconds: float) -> tuple[bool, float | None]:
        until = clock() + int(seconds * 1_000_000_000)
        while clock() < until and not expired():
            sleeper(TICK_S)
            parsed = snapshot()
            if payload.get("aborted"):
                return False, None
            if parsed is None:
                return False, None
            if _alive_target(parsed):
                hp = parsed.target_hp_ratio
                if hp is not None and hp >= ENGAGE_HP_MIN:
                    return True, hp
        return False, None

    add_step(
        "verify_search_start",
        session_s=SEARCH_SESSION_S,
        farm=False,
        rotation_type="keyboard_arrow",
        walk_ms=SEARCH_WALK_MS,
        arrow_ms=SEARCH_ARROW_MS,
        max_steps=SEARCH_MAX_STEPS,
    )

    locked = False
    initial: float | None = None
    ev = _send(backend, TargetSelect(method=TargetMethod.NEXT_HOTKEY), payload)
    if ev is None:
        return abort_now()
    payload["f1_pulses"] = int(payload["f1_pulses"]) + 1
    add_step("F1", hid_sent=ev.hid_sent, attempt=1, phase="scan")
    locked, initial = wait_lock(SEARCH_SCAN_S)
    if payload.get("aborted"):
        return abort_now()
    if locked:
        payload["target_locked"] = True
        payload["target_name_detected"] = True
        payload["initial_target_hp"] = initial
        payload["final_target_hp"] = initial
        add_step("locked", target_hp=initial, before_search=True)
        ev = backend.rotate_camera_keyboard("right", SEARCH_ARROW_MS, sleeper=sleeper)
        payload["hid_sent"] = bool(payload.get("hid_sent") or ev.hid_sent)
        if ev.reason == "kill_switch":
            payload["aborted"] = "kill_switch"
            return abort_now()
        if not ev.accepted:
            payload["aborted"] = ev.reason
            return abort_now()
        payload["rotation_sent"] = True
        payload["search_maneuver_executed"] = True
        payload["search_maneuver_triggered"] = True
        add_step("right_arrow", hid_sent=ev.hid_sent, duration_ms=SEARCH_ARROW_MS, reason="locked_q5")
    else:
        for step in range(1, SEARCH_MAX_STEPS + 1):
            payload["search_maneuver_triggered"] = True
            add_step("search_maneuver_triggered", search_step=step, f1_misses=int(payload["f1_pulses"]))
            ev = backend.rotate_camera_keyboard("right", SEARCH_ARROW_MS, sleeper=sleeper)
            payload["hid_sent"] = bool(payload.get("hid_sent") or ev.hid_sent)
            if ev.reason == "kill_switch":
                payload["aborted"] = "kill_switch"
                return abort_now()
            if not ev.accepted:
                payload["aborted"] = ev.reason
                return abort_now()
            payload["rotation_sent"] = True
            add_step("right_arrow", hid_sent=ev.hid_sent, duration_ms=SEARCH_ARROW_MS, search_step=step)
            if not _hold_key_ms(
                backend,
                payload,
                clock,
                sleeper,
                expired,
                focus,
                key="w",
                duration_ms=SEARCH_WALK_MS,
            ):
                return abort_now()
            payload["walk_step_sent"] = True
            payload["search_maneuver_executed"] = True
            add_step("HoldKey", key="w", hid_sent=True, duration_ms=SEARCH_WALK_MS, search_step=step)
            if pause(SEARCH_SETTLE_S):
                if payload.get("aborted"):
                    return abort_now()
                payload["aborted"] = payload.get("aborted") or "session_timeout"
                return abort_now()
            ev = _send(backend, TargetSelect(method=TargetMethod.NEXT_HOTKEY), payload)
            if ev is None:
                return abort_now()
            payload["f1_pulses"] = int(payload["f1_pulses"]) + 1
            add_step("F1", hid_sent=ev.hid_sent, attempt=int(payload["f1_pulses"]), phase="after_search", search_step=step)
            locked, initial = wait_lock(SEARCH_POST_S)
            if payload.get("aborted"):
                return abort_now()
            if locked:
                payload["target_acquired_after_search"] = True
                payload["target_locked"] = True
                payload["target_name_detected"] = True
                payload["initial_target_hp"] = initial
                payload["final_target_hp"] = initial
                add_step("locked", target_hp=initial, after_search=True)
                break

    if not locked:
        payload["aborted"] = "search_no_target"
        add_step("abort", reason="search_no_target", steps=SEARCH_MAX_STEPS)
        ev = _tap_escape(backend, payload)
        if ev is not None:
            add_step("Escape", hid_sent=ev.hid_sent, reason="search_no_target")
        return _finish(payload, out_path, clock, started, backend)

    for pulse in (1, 2):
        ev = _send(backend, SkillActivate(slot=2, key="F2", duration_ms=40), payload)
        if ev is None:
            return abort_now()
        payload["f2_pulses"] = int(payload["f2_pulses"]) + 1
        add_step("F2", hid_sent=ev.hid_sent, pulse=pulse)
        if pause(ENGAGE_F2_GAP_S) and payload.get("aborted"):
            return abort_now()

    hub.clear()
    combat_started = clock()
    last_hp = initial
    killed = False
    while _ms(clock(), combat_started) < MULTI_COMBAT_S * 1000.0 and not expired():
        sleeper(TICK_S)
        parsed = snapshot()
        if payload.get("aborted"):
            return abort_now()
        if parsed is None:
            break
        hp = parsed.target_hp_ratio
        payload["final_target_hp"] = hp
        if (
            last_hp is not None
            and hp is not None
            and last_hp - hp >= ENGAGE_DAMAGE_EPS
            and not payload["damage_detected"]
        ):
            payload["damage_detected"] = True
            payload["f2_to_hp_drop_ms"] = _ms(clock(), combat_started)
            add_step("hp_delta", from_hp=last_hp, to_hp=hp)
        last_hp = hp if hp is not None else last_hp
        if parsed.target_dead or (hp is not None and hp <= 0.0) or hub.get_latest(EntityDefeated) is not None:
            killed = True
            payload["target_killed"] = True
            payload["entity_defeated"] = True
            payload["time_to_kill_ms"] = _ms(clock(), combat_started)
            add_step("target_dead", target_hp=hp, time_to_kill_ms=payload["time_to_kill_ms"])
            break

    if not killed:
        payload["aborted"] = "kill_timeout"
        add_step("abort", reason="kill_timeout", target_hp=last_hp)
        ev = _tap_escape(backend, payload)
        if ev is not None:
            add_step("Escape", hid_sent=ev.hid_sent, reason="kill_timeout")
        return _finish(payload, out_path, clock, started, backend)

    if pause(MULTI_LOOT_DROP_S) and payload.get("aborted"):
        return abort_now()
    ev = _send(backend, SkillActivate(slot=3, key="F3", duration_ms=40), payload)
    if ev is None:
        return abort_now()
    payload["loot_pickup_sent"] = True
    payload["loot_actions_sent"] = 1
    add_step("F3", hid_sent=ev.hid_sent)
    if pause(LOOT_SETTLE_S) and payload.get("aborted"):
        return abort_now()

    ev = _tap_escape(backend, payload)
    if ev is None:
        return abort_now()
    payload["kills_completed"] = 1
    add_step("Escape", hid_sent=ev.hid_sent, reason="reset")
    payload["ok"] = True
    add_step("done", kills_completed=1, search_maneuver_executed=True)
    return _finish(payload, out_path, clock, started, backend)


def _run_spot_series(
    *,
    payload: dict[str, Any],
    backend: CGEventInputBackend,
    hub: TelemetryHub,
    clock: Callable[[], int],
    started: int,
    sleeper: Callable[[float], None],
    snapshot: Callable[[], HUDParseResult | None],
    expired: Callable[[], bool],
    add_step: Callable[..., None],
    out_path: Path | None,
    focus: Callable[[], bool],
    kill_target: int,
) -> dict[str, Any]:
    """SCAN → SEARCH_ROAM → COMBAT → LOOT, at most 5 kills / 180 s. Pulsed w. No farm."""

    def abort_now() -> dict[str, Any]:
        add_step("abort", reason=payload.get("aborted"))
        return _finish_roam(payload, out_path, clock, started, backend)

    def pause(seconds: float) -> bool:
        until = clock() + int(seconds * 1_000_000_000)
        while clock() < until:
            if expired() or payload.get("aborted"):
                return True
            sleeper(TICK_S)
            parsed = snapshot()
            if parsed is None:
                return True
            hp = parsed.self_hp_ratio
            if hp is not None and hp < ROAM_SELF_HP_ABORT:
                payload["aborted"] = "self_hp_low"
                return True
        return bool(payload.get("aborted") or expired())

    def wait_lock(seconds: float) -> tuple[bool, float | None]:
        until = clock() + int(seconds * 1_000_000_000)
        last_hp: float | None = None
        while clock() < until and not expired():
            sleeper(TICK_S)
            parsed = snapshot()
            if payload.get("aborted"):
                return False, None
            if parsed is None:
                return False, None
            if parsed.self_hp_ratio is not None and parsed.self_hp_ratio < ROAM_SELF_HP_ABORT:
                payload["aborted"] = "self_hp_low"
                return False, None
            if _alive_target(parsed):
                hp = parsed.target_hp_ratio
                if hp is not None and hp >= ENGAGE_HP_MIN:
                    return True, hp
                last_hp = hp
        return False, last_hp

    def tap_f2() -> bool:
        ev = _send(backend, SkillActivate(slot=2, key="F2", duration_ms=40), payload)
        if ev is None:
            return False
        payload["f2_pulses"] = int(payload["f2_pulses"]) + 1
        add_step("F2", hid_sent=ev.hid_sent, pulse=int(payload["f2_pulses"]))
        return True

    payload["rotation_type"] = "keyboard_arrow"
    payload["walk"] = True
    payload["farm"] = False
    add_step(
        "spot_series_start",
        cap=kill_target,
        session_s=ROAM_SESSION_S,
        farm=False,
        no_heal=True,
        walk_ms=ROAM_WALK_MS,
        arrow_ms=ROAM_ARROW_MS,
        roam_fail_limit=ROAM_FAIL_LIMIT,
    )

    failed_search = 0
    roam_total = 0
    combat_secs: list[float] = []

    while int(payload["kills_completed"]) < kill_target and not expired() and not payload.get("aborted"):
        cycle = int(payload["kills_completed"]) + 1
        search_started = clock()
        roam_before = roam_total
        add_step("SCAN", cycle=cycle)
        locked = False
        initial: float | None = None
        for attempt in range(1, ROAM_SCAN_F1 + 1):
            ev = _send(backend, TargetSelect(method=TargetMethod.NEXT_HOTKEY), payload)
            if ev is None:
                return abort_now()
            payload["f1_pulses"] = int(payload["f1_pulses"]) + 1
            add_step("F1", hid_sent=ev.hid_sent, cycle=cycle, attempt=attempt, phase="SCAN")
            locked, initial = wait_lock(ROAM_SCAN_S)
            if payload.get("aborted"):
                return abort_now()
            if locked:
                payload["target_locked"] = True
                payload["target_name_detected"] = True
                if payload["initial_target_hp"] is None:
                    payload["initial_target_hp"] = initial
                payload["final_target_hp"] = initial
                add_step("locked", cycle=cycle, target_hp=initial, attempt=attempt, phase="SCAN")
                failed_search = 0
                break
        search_ms = _ms(clock(), search_started)
        if not locked:
            if failed_search >= ROAM_FAIL_LIMIT:
                payload["aborted"] = "roam_limit"
                add_step("abort", reason="roam_limit", roam_cycles=roam_total)
                return abort_now()
            add_step("SEARCH_ROAM", cycle=cycle, failed_search=failed_search + 1)
            direction = "right" if roam_total % 2 == 0 else "left"
            ev = backend.rotate_camera_keyboard(direction, ROAM_ARROW_MS, sleeper=sleeper)
            payload["hid_sent"] = bool(payload.get("hid_sent") or ev.hid_sent)
            if ev.reason == "kill_switch":
                payload["aborted"] = "kill_switch"
                return abort_now()
            if not ev.accepted:
                payload["aborted"] = ev.reason
                return abort_now()
            payload["rotation_sent"] = True
            add_step(
                "arrow",
                hid_sent=ev.hid_sent,
                key=f"{direction}_arrow",
                duration_ms=ROAM_ARROW_MS,
                cycle=cycle,
            )
            for step in range(1, ROAM_WALK_PULSES + 1):
                if not _hold_key_ms(
                    backend,
                    payload,
                    clock,
                    sleeper,
                    expired,
                    focus,
                    key="w",
                    duration_ms=ROAM_WALK_MS,
                ):
                    return abort_now()
                payload["walk_step_sent"] = True
                add_step(
                    "HoldKey",
                    key="w",
                    hid_sent=True,
                    duration_ms=ROAM_WALK_MS,
                    cycle=cycle,
                    pulse=step,
                    phase="SEARCH_ROAM",
                )
                if step < ROAM_WALK_PULSES and pause(ROAM_WALK_GAP_S) and payload.get("aborted"):
                    return abort_now()
            roam_total += 1
            failed_search += 1
            payload["roam_cycles"] = roam_total
            payload["search_maneuver_executed"] = True
            continue

        combat_started = clock()
        add_step("COMBAT", cycle=cycle, target_hp=initial)
        for _ in (1, 2):
            if not tap_f2():
                return abort_now()
            if pause(ENGAGE_F2_GAP_S) and payload.get("aborted"):
                return abort_now()
        hub.clear()
        last_hp = initial
        last_drop_at = clock()
        killed = False
        while _ms(clock(), combat_started) < ROAM_COMBAT_MAX_S * 1000.0 and not expired():
            sleeper(TICK_S)
            parsed = snapshot()
            if payload.get("aborted"):
                return abort_now()
            if parsed is None:
                break
            if parsed.self_hp_ratio is not None and parsed.self_hp_ratio < ROAM_SELF_HP_ABORT:
                payload["aborted"] = "self_hp_low"
                return abort_now()
            hp = parsed.target_hp_ratio
            payload["final_target_hp"] = hp
            if last_hp is not None and hp is not None and last_hp - hp >= ENGAGE_DAMAGE_EPS:
                last_drop_at = clock()
                if not payload["damage_detected"]:
                    payload["damage_detected"] = True
                    payload["f2_to_hp_drop_ms"] = _ms(clock(), combat_started)
                    add_step("hp_delta", cycle=cycle, from_hp=last_hp, to_hp=hp)
            last_hp = hp if hp is not None else last_hp
            vanished = (
                not parsed.target_locked
                and last_hp is not None
                and last_hp <= ROAM_VANISH_HP
            )
            if (
                parsed.target_dead
                or (hp is not None and hp <= 0.0)
                or vanished
                or hub.get_latest(EntityDefeated) is not None
            ):
                killed = True
                payload["target_killed"] = True
                payload["entity_defeated"] = True
                payload["time_to_kill_ms"] = _ms(clock(), combat_started)
                add_step(
                    "target_dead",
                    cycle=cycle,
                    target_hp=hp,
                    time_to_kill_ms=payload["time_to_kill_ms"],
                )
                break
            if _ms(clock(), last_drop_at) >= ROAM_COMBAT_NO_DAMAGE_S * 1000.0:
                add_step("f2_retry", cycle=cycle, target_hp=hp)
                if not tap_f2():
                    return abort_now()
                last_drop_at = clock()
        combat_ms = _ms(clock(), combat_started)
        if not killed:
            add_step("combat_timeout", cycle=cycle, target_hp=last_hp)
            ev = _tap_escape(backend, payload)
            if ev is None:
                return abort_now()
            add_step("Escape", hid_sent=ev.hid_sent, cycle=cycle, reason="combat_timeout")
            if pause(MULTI_RESET_S) and payload.get("aborted"):
                return abort_now()
            continue

        loot_started = clock()
        add_step("LOOT", cycle=cycle)
        if pause(MULTI_LOOT_DROP_S) and payload.get("aborted"):
            return abort_now()
        for tap in range(1, ROAM_LOOT_TAPS + 1):
            ev = _send(backend, SkillActivate(slot=3, key="F3", duration_ms=40), payload)
            if ev is None:
                return abort_now()
            payload["loot_pickup_sent"] = True
            payload["loot_actions_sent"] = int(payload["loot_actions_sent"]) + 1
            add_step("F3", hid_sent=ev.hid_sent, cycle=cycle, tap=tap)
            if tap < ROAM_LOOT_TAPS and pause(ROAM_LOOT_GAP_S) and payload.get("aborted"):
                return abort_now()
        if pause(ROAM_LOOT_SETTLE_S) and payload.get("aborted"):
            return abort_now()
        ev = _tap_escape(backend, payload)
        if ev is None:
            return abort_now()
        loot_ms = _ms(clock(), loot_started)
        payload["kills_completed"] = int(payload["kills_completed"]) + 1
        payload["total_kills"] = payload["kills_completed"]
        combat_secs.append(combat_ms / 1000.0)
        frag = {
            "kill": payload["kills_completed"],
            "search_ms": search_ms,
            "combat_ms": combat_ms,
            "loot_ms": loot_ms,
            "roam_cycles": roam_total - roam_before,
            "initial_hp": initial,
            "final_hp": 0.0,
        }
        payload["frags"].append(frag)
        add_step(
            "frag",
            hid_sent=ev.hid_sent,
            cycle=cycle,
            kills_completed=payload["kills_completed"],
            search_ms=search_ms,
            combat_ms=combat_ms,
            loot_ms=loot_ms,
        )
        if payload["kills_completed"] >= kill_target:
            break
        if pause(MULTI_RESET_S) and payload.get("aborted"):
            return abort_now()

    if payload.get("aborted"):
        return abort_now()
    if payload["kills_completed"] >= kill_target:
        payload["ok"] = True
        add_step(
            "done",
            kills_completed=payload["kills_completed"],
            roam_cycles=roam_total,
            farm=False,
        )
    else:
        payload["aborted"] = "session_timeout"
        add_step(
            "abort",
            reason="session_timeout",
            kills_completed=payload["kills_completed"],
            roam_cycles=roam_total,
        )
    return _finish_roam(payload, out_path, clock, started, backend)


def _finish_roam(
    payload: dict[str, Any],
    out_path: Path | None,
    clock: Callable[[], int],
    started: int,
    backend: CGEventInputBackend | None,
) -> dict[str, Any]:
    payload["total_kills"] = int(payload.get("kills_completed") or 0)
    frags = list(payload.get("frags") or [])
    if frags:
        payload["avg_combat_duration_sec"] = float(
            sum(float(row.get("combat_ms") or 0.0) for row in frags) / (1000.0 * len(frags))
        )
    finished = _finish(payload, out_path, clock, started, backend)
    finished["elapsed_time_sec"] = float(finished.get("session_ms") or 0.0) / 1000.0
    if out_path is not None:
        out_path.write_text(json.dumps(finished, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return finished


def _hold_key_ms(
    backend: CGEventInputBackend,
    payload: dict[str, Any],
    clock: Callable[[], int],
    sleeper: Callable[[float], None],
    expired: Callable[[], bool],
    focus: Callable[[], bool],
    *,
    key: str,
    duration_ms: int,
) -> bool:
    """Hold a key for duration_ms (<=500). Heartbeat so the 250ms watchdog does not trip."""
    hold_ms = min(max(int(duration_ms), 1), SEARCH_HOLD_MAX_MS)
    ev = _send(backend, HoldKey(key=key, duration_ms=hold_ms, state="down"), payload)
    if ev is None:
        return False
    until = clock() + int(hold_ms * 1_000_000)
    while clock() < until:
        if expired():
            payload["aborted"] = payload.get("aborted") or "session_timeout"
            backend.watchdog.heartbeat(clock())
            _send(backend, HoldKey(key=key, state="up"), payload)
            return False
        if not focus():
            payload["aborted"] = "focus_lost"
            backend.release_all()
            return False
        backend.watchdog.heartbeat(clock())
        sleeper(TICK_S)
    backend.watchdog.heartbeat(clock())
    up = _send(backend, HoldKey(key=key, state="up"), payload)
    return up is not None


def _run_multi_kill(
    *,
    payload: dict[str, Any],
    backend: CGEventInputBackend,
    hub: TelemetryHub,
    clock: Callable[[], int],
    started: int,
    sleeper: Callable[[float], None],
    snapshot: Callable[[], HUDParseResult | None],
    expired: Callable[[], bool],
    add_step: Callable[..., None],
    out_path: Path | None,
    kill_target: int,
) -> dict[str, Any]:
    """At most MULTI_KILL_CAP kills or MULTI_SESSION_S. Not a farm loop."""

    def abort_now() -> dict[str, Any]:
        add_step("abort", reason=payload.get("aborted"))
        return _finish(payload, out_path, clock, started, backend)

    def pause(seconds: float) -> bool:
        until = clock() + int(seconds * 1_000_000_000)
        while clock() < until:
            if expired() or payload.get("aborted"):
                return True
            sleeper(TICK_S)
            if snapshot() is None:
                return True
        return bool(payload.get("aborted") or expired())

    add_step("multi_kill_start", cap=kill_target, session_s=MULTI_SESSION_S, farm=False)

    while payload["kills_completed"] < kill_target and not expired() and not payload.get("aborted"):
        cycle = int(payload["kills_completed"]) + 1
        add_step("scan", cycle=cycle)
        locked = False
        initial: float | None = None
        f1_attempts = 0
        while not locked and not expired() and not payload.get("aborted"):
            ev = _send(backend, TargetSelect(method=TargetMethod.NEXT_HOTKEY), payload)
            if ev is None:
                return abort_now()
            f1_attempts += 1
            payload["f1_pulses"] = int(payload["f1_pulses"]) + 1
            add_step("F1", hid_sent=ev.hid_sent, cycle=cycle, attempt=f1_attempts)
            scan_until = clock() + int(MULTI_SCAN_S * 1_000_000_000)
            while clock() < scan_until and not expired():
                sleeper(TICK_S)
                parsed = snapshot()
                if payload.get("aborted"):
                    return abort_now()
                if parsed is None:
                    break
                if _alive_target(parsed):
                    hp = parsed.target_hp_ratio
                    if hp is not None and hp >= ENGAGE_HP_MIN:
                        locked = True
                        initial = hp
                        payload["target_locked"] = True
                        payload["target_name_detected"] = True
                        if payload["initial_target_hp"] is None:
                            payload["initial_target_hp"] = hp
                        payload["final_target_hp"] = hp
                        add_step("locked", cycle=cycle, target_hp=hp, attempt=f1_attempts)
                        break
            if locked:
                break
            if f1_attempts % MULTI_F1_ATTEMPTS == 0:
                ev = backend.rotate_camera_keyboard("right", MULTI_ARROW_MS, sleeper=sleeper)
                payload["hid_sent"] = bool(payload.get("hid_sent") or ev.hid_sent)
                if ev.reason == "kill_switch":
                    payload["aborted"] = "kill_switch"
                    return abort_now()
                if not ev.accepted:
                    payload["aborted"] = ev.reason
                    return abort_now()
                add_step("right_arrow", hid_sent=ev.hid_sent, cycle=cycle, duration_ms=MULTI_ARROW_MS)
                if pause(0.20):
                    break

        if payload.get("aborted"):
            return abort_now()
        if not locked:
            payload["aborted"] = payload.get("aborted") or "session_timeout"
            add_step("abort", reason=payload["aborted"], cycle=cycle, phase="scan")
            return _finish(payload, out_path, clock, started, backend)

        for pulse in (1, 2):
            ev = _send(backend, SkillActivate(slot=2, key="F2", duration_ms=40), payload)
            if ev is None:
                return abort_now()
            payload["f2_pulses"] = int(payload["f2_pulses"]) + 1
            add_step("F2", hid_sent=ev.hid_sent, cycle=cycle, pulse=pulse)
            if pause(ENGAGE_F2_GAP_S):
                if payload.get("aborted"):
                    return abort_now()
                break

        hub.clear()
        combat_started = clock()
        last_hp = initial
        killed = False
        defeated = False
        while _ms(clock(), combat_started) < MULTI_COMBAT_S * 1000.0 and not expired():
            sleeper(TICK_S)
            parsed = snapshot()
            if payload.get("aborted"):
                return abort_now()
            if parsed is None:
                break
            hp = parsed.target_hp_ratio
            payload["final_target_hp"] = hp
            if (
                last_hp is not None
                and hp is not None
                and last_hp - hp >= ENGAGE_DAMAGE_EPS
                and not payload["damage_detected"]
            ):
                payload["damage_detected"] = True
                payload["f2_to_hp_drop_ms"] = _ms(clock(), combat_started)
                add_step("hp_delta", cycle=cycle, from_hp=last_hp, to_hp=hp)
            last_hp = hp if hp is not None else last_hp
            if parsed.target_dead or (hp is not None and hp <= 0.0):
                killed = True
            if hub.get_latest(EntityDefeated) is not None:
                killed = True
                defeated = True
            if killed:
                payload["target_killed"] = True
                payload["entity_defeated"] = bool(payload["entity_defeated"] or defeated or parsed.target_dead)
                payload["time_to_kill_ms"] = _ms(clock(), combat_started)
                add_step(
                    "target_dead",
                    cycle=cycle,
                    target_hp=hp,
                    entity_defeated=payload["entity_defeated"],
                    time_to_kill_ms=payload["time_to_kill_ms"],
                )
                break

        if not killed:
            add_step("combat_timeout", cycle=cycle, target_hp=last_hp)
            ev = _tap_escape(backend, payload)
            if ev is None:
                return abort_now()
            add_step("Escape", hid_sent=ev.hid_sent, cycle=cycle, reason="combat_timeout")
            payload["cycles"].append(
                {"cycle": cycle, "killed": False, "loot": False, "initial_hp": initial, "final_hp": last_hp}
            )
            if pause(MULTI_RESET_S):
                if payload.get("aborted"):
                    return abort_now()
                break
            continue

        if pause(MULTI_LOOT_DROP_S):
            if payload.get("aborted"):
                return abort_now()
            break
        ev = _send(backend, SkillActivate(slot=3, key="F3", duration_ms=40), payload)
        if ev is None:
            return abort_now()
        payload["loot_pickup_sent"] = True
        payload["loot_actions_sent"] = int(payload["loot_actions_sent"]) + 1
        add_step("F3", hid_sent=ev.hid_sent, cycle=cycle)
        if pause(LOOT_SETTLE_S) and payload.get("aborted"):
            return abort_now()

        ev = _tap_escape(backend, payload)
        if ev is None:
            return abort_now()
        payload["kills_completed"] = int(payload["kills_completed"]) + 1
        add_step(
            "frag",
            hid_sent=ev.hid_sent,
            cycle=cycle,
            kills_completed=payload["kills_completed"],
            loot_actions_sent=payload["loot_actions_sent"],
            time_to_kill_ms=payload["time_to_kill_ms"],
        )
        payload["cycles"].append(
            {
                "cycle": cycle,
                "killed": True,
                "loot": True,
                "initial_hp": initial,
                "final_hp": 0.0,
                "time_to_kill_ms": payload["time_to_kill_ms"],
            }
        )
        if payload["kills_completed"] >= kill_target:
            break
        if pause(MULTI_RESET_S):
            if payload.get("aborted"):
                return abort_now()
            break

    if payload.get("aborted"):
        return abort_now()
    if payload["kills_completed"] >= kill_target:
        payload["ok"] = True
        add_step("done", kills_completed=payload["kills_completed"])
    else:
        payload["aborted"] = "session_timeout"
        add_step(
            "abort",
            reason="session_timeout",
            kills_completed=payload["kills_completed"],
        )
    return _finish(payload, out_path, clock, started, backend)


def _alive_target(parsed: HUDParseResult) -> bool:
    """Living plate with HP. Empty/dead plate after Escape is a clear."""
    if not parsed.target_locked or parsed.target_dead:
        return False
    hp = parsed.target_hp_ratio
    return hp is not None and hp > 0.0


def _tap_escape(backend: CGEventInputBackend, payload: dict[str, Any]) -> Any | None:
    ev = _send(backend, HoldKey(key="escape", state="down"), payload)
    if ev is None:
        return None
    up = _send(backend, HoldKey(key="escape", state="up"), payload)
    return ev if up is not None else None


def _send(backend: CGEventInputBackend, action: Any, payload: dict[str, Any]) -> Any | None:
    event = backend.send_action(action)
    payload["hid_sent"] = bool(payload.get("hid_sent") or event.hid_sent)
    if event.reason == "kill_switch":
        payload["aborted"] = "kill_switch"
        return None
    if not event.accepted:
        payload["aborted"] = event.reason
        return None
    return event


def _ms(now: int, start: int) -> float:
    return (now - start) / 1_000_000.0


def _finish(
    payload: dict[str, Any],
    out_path: Path | None,
    clock: Callable[[], int],
    started: int,
    backend: CGEventInputBackend | None,
) -> dict[str, Any]:
    if backend is not None:
        try:
            if payload.get("aborted") and payload["aborted"] not in ("live_flags_required", "no_target_pid"):
                backend.send_action(EmergencyStop(reason=str(payload["aborted"])))
            backend.release_all()
        except Exception:  # noqa: BLE001 — probe must still write the report
            pass
        payload["stuck_keys_count"] = len(backend.watchdog.active_holds)
        payload["watchdog_tripped"] = bool(
            payload.get("watchdog_tripped")
            or any(row.reason == "watchdog_timeout" for row in backend.log)
        )
        payload["events"] = backend.events()
        payload["hid_sent"] = bool(payload.get("hid_sent") or any(row.hid_sent for row in backend.log))
    payload["session_ms"] = _ms(clock(), started)
    payload["total_session_ms"] = payload["session_ms"]
    payload["final_hp"] = payload.get("final_target_hp")
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["out"] = str(out_path)
    return payload
