from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from l2_brain.sim.config import SCENARIO_ALIASES, EpisodeSpec, Split
from l2_brain.sim.world import Box


@dataclass(frozen=True, slots=True)
class Layout:
    start_xy: tuple[float, float]
    start_yaw: float
    goal_xy: tuple[float, float]
    walls: tuple[Box, ...]
    hide_goal_after: int | None = None
    goal_delta: tuple[float, float] | None = None
    camera_only_turn: bool = False
    texture_strength: float | None = None
    lighting: float | None = None
    action_delay_ticks: int | None = None
    drop_ticks: tuple[int, ...] | None = None


def layout_for(spec: EpisodeSpec) -> Layout:
    name = SCENARIO_ALIASES.get(spec.scenario, spec.scenario)
    base = _BASE[name]()
    rng = np.random.default_rng(_mix_seed(spec.seed, spec.scenario, spec.variant, spec.split))
    return _vary(base, spec.split, spec.variant, rng)


def _mix_seed(seed: int, scenario: str, variant: int, split: Split) -> int:
    payload = f"{seed}:{scenario}:{variant}:{split}".encode()
    digest = hashlib.blake2s(payload, digest_size=8).digest()
    return int.from_bytes(digest, "little") % (2**31)


def _vary(layout: Layout, split: Split, variant: int, rng: np.random.Generator) -> Layout:
    jitter = 0.08 + 0.05 * variant
    dy = float(rng.normal(0.0, jitter))
    yaw = layout.start_yaw + float(rng.normal(0.0, 0.04 + 0.02 * variant))
    sx, sy = layout.start_xy
    gx, gy = layout.goal_xy
    if split == "held_out":
        sy = 16.0 - sy
        gy = 16.0 - gy
        walls = tuple(Box(b.x0, 16.0 - b.y1, b.x1, 16.0 - b.y0, b.kind) for b in layout.walls)
        yaw = -yaw
    else:
        walls = layout.walls
        sy += dy
        gy += dy * 0.5
    return Layout(
        start_xy=(sx, float(np.clip(sy, 1.5, 14.5))),
        start_yaw=yaw,
        goal_xy=(gx, float(np.clip(gy, 1.5, 14.5))),
        walls=walls,
        hide_goal_after=layout.hide_goal_after,
        goal_delta=layout.goal_delta,
        camera_only_turn=layout.camera_only_turn,
        texture_strength=layout.texture_strength,
        lighting=layout.lighting,
        action_delay_ticks=layout.action_delay_ticks,
        drop_ticks=layout.drop_ticks,
    )


def _open() -> Layout:
    return Layout((3.4, 8.0), 0.0, (10.2, 8.0), ())


def _obstacle() -> Layout:
    return Layout((3.4, 8.0), 0.0, (11.0, 8.0), (Box(6.7, 7.35, 7.5, 8.65),))


def _gate() -> Layout:
    return Layout(
        (3.4, 8.0),
        0.0,
        (11.2, 8.0),
        (Box(7.0, 1.0, 7.6, 7.25), Box(7.0, 8.75, 7.6, 15.0)),
    )


def _corridor() -> Layout:
    return Layout(
        (3.3, 8.0),
        0.0,
        (12.0, 8.0),
        (Box(3.0, 6.15, 12.5, 6.65), Box(3.0, 9.35, 12.5, 9.85)),
    )


def _fence() -> Layout:
    return Layout((3.4, 8.0), 0.0, (11.4, 8.0), (Box(6.6, 4.2, 7.15, 12.6),))


def _u_trap() -> Layout:
    return Layout(
        (6.4, 8.0),
        0.0,
        (3.2, 8.0),
        (
            Box(7.5, 6.4, 8.15, 9.6),
            Box(5.1, 6.4, 8.15, 6.95),
            Box(5.1, 9.05, 8.15, 9.6),
        ),
    )


def _dead_end() -> Layout:
    return Layout(
        (8.6, 8.0),
        0.0,
        (3.2, 8.0),
        (
            Box(3.5, 6.3, 10.4, 6.8),
            Box(3.5, 9.2, 10.4, 9.7),
            Box(10.0, 6.3, 10.5, 9.7),
        ),
    )


def _weak() -> Layout:
    return Layout(
        (3.4, 8.0),
        0.0,
        (11.0, 8.0),
        (Box(6.7, 7.2, 7.5, 8.8),),
        texture_strength=0.07,
        lighting=0.55,
    )


def _moving() -> Layout:
    return Layout((3.4, 8.0), 0.0, (8.0, 6.4), (), goal_delta=(0.0, 0.035))


def _vanish() -> Layout:
    return Layout((3.4, 8.0), 0.0, (9.4, 8.0), (), hide_goal_after=8)


def _spin() -> Layout:
    return Layout((5.0, 8.0), 0.0, (10.0, 8.0), (), camera_only_turn=True)


def _latency() -> Layout:
    return Layout(
        (3.4, 8.0),
        0.0,
        (10.0, 8.0),
        (),
        action_delay_ticks=2,
        drop_ticks=(4, 9, 14, 20),
    )


def _detour() -> Layout:
    """Visible goal, straight line blocked. Must leave the bearing and hold a side."""
    return Layout((3.4, 8.0), 0.0, (11.0, 12.0), (Box(6.4, 6.8, 7.2, 9.2),))


def _jog() -> Layout:
    """Visible goal at the end of a right jog. Side must be held; reverse not required."""
    return Layout(
        (3.2, 8.0),
        0.0,
        (10.8, 10.6),
        (
            Box(3.0, 6.3, 12.4, 6.8),
            Box(3.0, 9.3, 7.2, 9.8),
            Box(7.2, 9.3, 7.7, 12.2),
            Box(7.2, 12.2, 12.4, 12.7),
            Box(12.0, 6.3, 12.5, 12.7),
        ),
    )


def _yard() -> Layout:
    """Closed yard with one exit. Easy to loop if the side flips."""
    return Layout(
        (5.0, 5.0),
        0.8,
        (11.0, 11.0),
        (
            Box(3.5, 3.5, 12.5, 4.0),
            Box(3.5, 12.0, 12.5, 12.5),
            Box(3.5, 3.5, 4.0, 12.5),
            Box(12.0, 3.5, 12.5, 8.6),
            Box(12.0, 10.0, 12.5, 12.5),
        ),
    )


def _push_wall() -> Layout:
    """Diagnostic only: wall immediately ahead. Not an autonomous catalog scene."""
    return Layout((4.0, 8.0), 0.0, (10.0, 8.0), (Box(4.45, 6.5, 5.2, 9.5),))


_BASE = {
    "open_goal": _open,
    "single_obstacle": _obstacle,
    "narrow_gate": _gate,
    "corridor": _corridor,
    "long_fence": _fence,
    "u_trap": _u_trap,
    "dead_end": _dead_end,
    "weak_texture": _weak,
    "moving_target": _moving,
    "vanishing_target": _vanish,
    "camera_spin": _spin,
    "latency_drops": _latency,
    "detour_visible": _detour,
    "side_hold_jog": _jog,
    "loop_yard": _yard,
    "push_wall": _push_wall,
}
