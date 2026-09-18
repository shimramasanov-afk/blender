"""Overlapping episode events. Not a single exclusive stuck label.

Ground-truth flags use evaluator traces only. Controller estimates use
diagnostics available to the policy, never pose or goal coordinates.
"""

from __future__ import annotations

import math
from typing import Any

# Documented clock. SimConfig.tick_hz default is 20.
# One control tick = 1 / tick_hz seconds. max_speed is units per tick, not per second.
DEFAULT_TICK_HZ = 20
PHYSICAL_BLOCK_S = 0.40
STAGNATION_S = 1.25
TARGET_UNOBSERVED_S = 0.50
SEARCHING_S = 0.50
INVALID_S = 0.20
POSE_MOVE_MAX = 0.025
CMD_FORWARD_MIN = 0.20
STAGNATION_DIST = 0.12


def seconds_per_tick(tick_hz: int = DEFAULT_TICK_HZ) -> float:
    if tick_hz < 1:
        raise ValueError("tick_hz must be >= 1")
    return 1.0 / float(tick_hz)


def ticks_for(seconds: float, tick_hz: int = DEFAULT_TICK_HZ) -> int:
    return max(2, int(round(seconds * tick_hz)))


def score_events(
    traces: list[dict[str, Any]],
    *,
    success: bool,
    timeout: bool,
    tick_hz: int = DEFAULT_TICK_HZ,
) -> dict[str, Any]:
    dt = seconds_per_tick(tick_hz)
    block_n = ticks_for(PHYSICAL_BLOCK_S, tick_hz)
    stag_n = ticks_for(STAGNATION_S, tick_hz)
    unobs_n = ticks_for(TARGET_UNOBSERVED_S, tick_hz)
    search_n = ticks_for(SEARCHING_S, tick_hz)
    invalid_n = ticks_for(INVALID_S, tick_hz)

    gt_block = _windows(_gt_block_flags(traces), block_n)
    gt_stag = _stagnation(traces, stag_n)
    gt_unobs = _windows([not bool(row.get("goal_visible", True)) or not bool(row.get("in_fov", True)) for row in traces], unobs_n)
    gt_invalid = _windows([bool(row.get("dropped") or row.get("stale")) for row in traces], invalid_n)

    ctl_search = _windows([row.get("reason") == "search" or row.get("situation") == "camera_turn" for row in traces], search_n)
    ctl_block = _windows([row.get("situation") == "blocked" or bool(row.get("recovering")) for row in traces], block_n)
    ctl_invalid = _windows([row.get("reason") == "stale" or bool(row.get("stale")) for row in traces], invalid_n)

    return {
        "clock": {
            "tick_hz": tick_hz,
            "seconds_per_tick": dt,
            "physical_block_s": PHYSICAL_BLOCK_S,
            "stagnation_s": STAGNATION_S,
            "target_unobserved_s": TARGET_UNOBSERVED_S,
            "searching_s": SEARCHING_S,
            "invalid_s": INVALID_S,
            "max_speed_is_units_per_tick": True,
        },
        "gt": {
            "physical_blockage": bool(gt_block),
            "physical_blockage_windows": len(gt_block),
            "navigation_stagnation": gt_stag,
            "target_unobserved": bool(gt_unobs),
            "observation_invalid": bool(gt_invalid),
            "episode_timeout": bool(timeout and not success),
        },
        "controller": {
            "searching": bool(ctl_search),
            "physical_blockage": bool(ctl_block),
            "observation_invalid": bool(ctl_invalid),
            "privileged": False,
        },
        "legacy_outcome_stuck_is_not_physical_blockage": True,
    }


def rate_or_na(numer: int, denom: int) -> float | None:
    if denom <= 0:
        return None
    return numer / denom


def _gt_block_flags(traces: list[dict[str, Any]]) -> list[bool]:
    flags: list[bool] = []
    for i, row in enumerate(traces):
        moved = 1.0
        if "previous_x" in row and "previous_y" in row:
            moved = math.hypot(row["x"] - row["previous_x"], row["y"] - row["previous_y"])
        elif i > 0:
            moved = math.hypot(row["x"] - traces[i - 1]["x"], row["y"] - traces[i - 1]["y"])
        flags.append(
            float(row.get("applied_forward", row.get("cmd_forward", 0.0))) >= CMD_FORWARD_MIN
            and moved < POSE_MOVE_MAX
            and float(row.get("dist", 1.0)) > 0.8
        )
    return flags


def _stagnation(traces: list[dict[str, Any]], window: int) -> bool:
    if len(traces) < window:
        return False
    dists = [float(row["dist"]) for row in traces]
    lo = dists[-window:]
    return min(lo) > lo[0] - STAGNATION_DIST


def _windows(flags: list[bool], min_len: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    start: int | None = None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = i
        if not flag and start is not None:
            if i - start >= min_len:
                out.append((start, i - 1))
            start = None
    if start is not None and len(flags) - start >= min_len:
        out.append((start, len(flags) - 1))
    return out
