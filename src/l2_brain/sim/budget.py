"""A priori time budgets. Do not raise timeout after seeing success."""

from __future__ import annotations

import math

from l2_brain.sim.config import SimConfig
from l2_brain.sim.scenarios import layout_for
from l2_brain.sim.config import EpisodeSpec


def straight_ticks(dist: float, cfg: SimConfig, *, cruise: float = 0.62) -> int:
    step = max(cfg.max_speed * cruise, 1e-6)
    return int(math.ceil(dist / step))


def lower_bound(spec: EpisodeSpec, *, cruise: float = 0.62, search_margin: float = 2.0) -> dict:
    """Geometry only. Privileged. Not a policy input."""
    layout = layout_for(spec)
    sx, sy = layout.start_xy
    gx, gy = layout.goal_xy
    dist = math.hypot(gx - sx, gy - sy)
    need = straight_ticks(dist, spec.config, cruise=cruise)
    yaw_err = abs(math.atan2(gy - sy, gx - sx) - layout.start_yaw)
    turn_ticks = int(math.ceil(yaw_err / max(spec.config.max_turn, 1e-6)))
    assigned = int(math.ceil((need + turn_ticks) * search_margin))
    return {
        "straight_dist": dist,
        "min_forward_ticks": need,
        "min_turn_ticks": turn_ticks,
        "assigned_ticks": assigned,
        "frozen_budget_ticks": 200,
        "seconds_per_tick": 1.0 / spec.config.tick_hz,
        "assigned_s": assigned / spec.config.tick_hz,
        "speed_units_per_tick": spec.config.max_speed,
        "note": "assigned before autonomous success; frozen 200 kept for F14/F15 compare",
    }
