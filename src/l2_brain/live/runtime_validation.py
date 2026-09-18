"""Diagnostic helpers for R1/R2 LiveRuntime validation. Not a Task layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

NPC_ID = "R1"
COMBAT_ID = "R2"
EVIDENCE_DIR = Path("docs/evidence/live-agent-runtime")
NPC_OUT = EVIDENCE_DIR / "R1-runtime-npc.json"
COMBAT_OUT = EVIDENCE_DIR / "R2-runtime-combat.json"


def print_banner(
    *,
    mode: str,
    window_id: int | None,
    target_pid: int | None,
    kill_cap: int | None,
    live: bool,
    danger_confirmed: bool,
) -> None:
    print("LIVE RUNTIME VALIDATION", flush=True)
    print(f"Window ID: {window_id if window_id is not None else 'unset'}", flush=True)
    print(f"PID: {target_pid if target_pid is not None else 'unset'}", flush=True)
    print(f"Mode: {mode}", flush=True)
    print(f"NPC / Combat: {mode}", flush=True)
    print(f"Kill cap: {kill_cap if kill_cap is not None else 'n/a'}", flush=True)
    print("Input backend: CGEventInputBackend", flush=True)
    print("Capture: SCKGrabber", flush=True)
    print(f"Safety flags: live={bool(live)} danger_confirmed={bool(danger_confirmed)}", flush=True)
    print("F12 stop: yes", flush=True)
    print("Watchdog: 250ms", flush=True)


def stamp_runtime_identity(payload: dict[str, Any], *, validation_id: str) -> None:
    payload["architecture"] = "LiveRuntime"
    payload["runtime_used"] = True
    payload["validation_id"] = validation_id
    payload.setdefault("skill_trace", [])
    payload.setdefault("capture_restart_attempts", 0)
    payload.setdefault("capture_restart_successes", 0)
    payload.setdefault("capture_recovery_used", False)
    payload.setdefault("focus_lost", False)
    payload.setdefault("capture_lost", False)
    payload.setdefault("runtime_abort_reason", None)
    payload.setdefault("release_all_called", False)
    payload.setdefault("frozen_used", False)
    payload.setdefault("snn_used", False)
    payload.setdefault("malecns_used", False)
    payload.setdefault("circuit_used", False)


def note_safety(payload: dict[str, Any]) -> None:
    aborted = payload.get("aborted")
    payload["focus_lost"] = aborted == "focus_lost"
    payload["capture_lost"] = aborted == "capture_lost"
    payload["runtime_abort_reason"] = aborted
    payload["capture_recovery_used"] = int(payload.get("capture_restart_successes") or 0) > 0


def npc_validation_result(payload: dict[str, Any]) -> str:
    """PASS / PARTIAL / FAIL for R1. Not a live-proven claim."""
    note_safety(payload)
    opened = payload.get("open_dialog_skill_status") == "success"
    clicked = payload.get("click_skill_status") == "success"
    closed_skill = payload.get("close_dialog_status") in {"success", "failed"}
    dialog_seen = bool(payload.get("dialog_detected"))
    items = int(payload.get("dialog_items_count") or payload.get("total_items_found") or 0)
    closed = bool(payload.get("dialog_closed"))
    focus_ok = not payload.get("focus_lost")
    runtime_ok = bool(payload.get("runtime_used"))
    target_ok = bool(payload.get("target_acquired") or payload.get("target_locked") or payload.get("chat_target_success"))
    talk = bool(payload.get("talk_click_sent") or payload.get("talk_click_dispatched"))
    f2_opened = bool(payload.get("f2_approach") and opened and dialog_seen)
    released = bool(payload.get("release_all_called"))
    chain = (
        runtime_ok
        and target_ok
        and opened
        and dialog_seen
        and items >= 1
        and clicked
        and (talk or f2_opened)
        and closed_skill
    )
    if chain and closed and focus_ok and released and payload.get("aborted") is None:
        return "PASS"
    if chain and dialog_seen and not closed:
        return "PARTIAL"
    return "FAIL"


def combat_validation_result(payload: dict[str, Any]) -> str:
    note_safety(payload)
    kills = int(payload.get("kills_completed") or 0)
    attack_ok = int(payload.get("attack_skill_success") or 0) >= 1
    loot_ok = int(payload.get("loot_skill_runs") or 0) >= 1
    stuck = int(payload.get("stuck_keys_count") or payload.get("stuck_keys") or 0)
    focus_ok = not payload.get("focus_lost")
    released = bool(payload.get("release_all_called"))
    farm = bool(payload.get("farm"))
    heal = bool(payload.get("heal_sent"))
    if (
        kills >= 1
        and attack_ok
        and loot_ok
        and stuck == 0
        and focus_ok
        and released
        and not farm
        and not heal
        and payload.get("aborted") is None
        and not payload.get("frozen_used")
        and not payload.get("snn_used")
        and not payload.get("malecns_used")
        and not payload.get("circuit_used")
    ):
        return "PASS"
    if kills >= 1 and (not attack_ok or not loot_ok or stuck or not released):
        return "PARTIAL"
    return "FAIL"
