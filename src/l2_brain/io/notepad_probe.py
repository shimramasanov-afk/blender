"""Notepad-only CGEvent probe. Refuses if a game process is visible in the guest."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from l2_brain.experiment.clocks import mono_ns
from l2_brain.io.actions import HoldKey
from l2_brain.io.cgevent_backend import CGEventInputBackend

# Guest image names that mean "do not send". Not a client adapter.
_GAME_MARKERS = ("l2.exe", "l2.bin", "lineage", "lin2.exe", "l2.exe *32")


def guest_tasklist(vm_name: str = "Windows 11") -> str:
    try:
        proc = subprocess.run(
            ["prlctl", "exec", vm_name, "cmd", "/c", "tasklist"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"tasklist_error:{exc}"
    return (proc.stdout or "") + (proc.stderr or "")


def game_markers_found(listing: str) -> list[str]:
    low = listing.lower()
    return [marker for marker in _GAME_MARKERS if marker in low]


def game_process_present(listing: str) -> bool:
    return bool(game_markers_found(listing))


def notepad_present(listing: str) -> bool:
    for line in listing.lower().splitlines():
        if "notepad.exe" in line and "console" in line:
            return True
    return False


def activate_parallels() -> bool:
    try:
        proc = subprocess.run(
            ["osascript", "-e", 'tell application "Parallels Desktop" to activate'],
            check=False,
            capture_output=True,
            text=True,
            timeout=3.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def ensure_notepad(vm_name: str = "Windows 11") -> dict[str, Any]:
    listing = guest_tasklist(vm_name)
    if listing.startswith("tasklist_error"):
        return {"ok": False, "reason": listing, "listing_head": listing[:200]}
    if game_process_present(listing):
        return {
            "ok": False,
            "reason": "game_process_present",
            "markers": game_markers_found(listing),
            "listing_head": listing[:400],
        }
    if notepad_present(listing):
        return {"ok": True, "reason": "notepad_already", "listing_head": listing[:200]}
    try:
        proc = subprocess.run(
            ["prlctl", "exec", vm_name, "--current-user", "cmd", "/c", "start", "", "notepad"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": f"start_notepad:{exc}", "listing_head": listing[:200]}
    if proc.returncode != 0:
        return {
            "ok": False,
            "reason": f"start_notepad_rc:{proc.returncode}",
            "listing_head": (proc.stderr or proc.stdout or "")[:200],
        }
    time.sleep(0.8)
    listing2 = guest_tasklist(vm_name)
    if game_process_present(listing2):
        return {"ok": False, "reason": "game_process_present_after_start"}
    return {
        "ok": notepad_present(listing2),
        "reason": "notepad_started" if notepad_present(listing2) else "notepad_not_seen",
        "listing_head": listing2[:200],
    }


def run_notepad_scenario(
    backend: CGEventInputBackend,
    *,
    sleeper: Callable[[float], None] = time.sleep,
    now_ns: Callable[[], int] | None = None,
) -> dict[str, Any]:
    clock = now_ns or mono_ns
    latencies: list[float] = []

    def send(action: HoldKey) -> None:
        t0 = clock()
        backend.send_action(action)
        latencies.append((clock() - t0) / 1_000_000.0)

    sleeper(1.0)
    if not backend.check_window_focus():
        return {
            "hid_sent": False,
            "aborted": "focus_not_parallels",
            "act_ms": [],
            "stuck_keys_count": len(backend.watchdog.active_holds),
        }
    for digit in ("1", "2", "3"):
        send(HoldKey(key=digit, duration_ms=0, state="down"))
        sleeper(0.04)
        send(HoldKey(key=digit, duration_ms=0, state="up"))
    send(HoldKey(key="w", duration_ms=0, state="down"))
    hold_t0 = clock()
    while (clock() - hold_t0) / 1_000_000.0 < 400.0:
        backend.watchdog.heartbeat(clock())
        sleeper(0.05)
    backend.release_all()
    send(HoldKey(key="w", duration_ms=0, state="down"))
    sleeper(0.30)
    tripped = backend.pump()
    stuck = len(backend.watchdog.active_holds)
    return {
        "hid_sent": any(row.hid_sent for row in backend.log),
        "aborted": None,
        "watchdog_tripped": tripped,
        "stuck_keys_count": stuck,
        "act_ms": latencies,
        "act_ms_p50": _pct(latencies, 0.50),
        "act_ms_p95": _pct(latencies, 0.95),
        "events": backend.events(),
        "release_count": backend.watchdog.release_count,
    }


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return float(ordered[idx])
