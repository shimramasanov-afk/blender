from __future__ import annotations

import math

import numpy as np

from l2_brain.sim.config import SimConfig
from l2_brain.sim.world import Box, ray_aabb_xy, ray_circle_xy


def render_perspective(
    *,
    x: float,
    y: float,
    camera_yaw: float,
    goal_x: float,
    goal_y: float,
    goal_visible: bool,
    walls: tuple[Box, ...],
    config: SimConfig,
) -> np.ndarray:
    """First-person pinhole camera. Not a top-down map. Not an MMORPG frame."""
    h, w = config.frame_h, config.frame_w
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    max_dist = 18.0
    oz = config.camera_height
    strength = config.texture_strength
    light = config.lighting
    for row in range(h):
        pitch = config.camera_pitch + (0.5 - row / max(h - 1, 1)) * config.fov_v
        cp = math.cos(pitch)
        sp = math.sin(pitch)
        for col in range(w):
            yaw = camera_yaw + (0.5 - col / max(w - 1, 1)) * config.fov_h
            dx = cp * math.cos(yaw)
            dy = cp * math.sin(yaw)
            dz = sp
            color = _trace(
                x,
                y,
                oz,
                dx,
                dy,
                dz,
                max_dist,
                walls,
                goal_x,
                goal_y,
                goal_visible,
                config,
                strength,
                light,
            )
            frame[row, col] = color
    return frame


def _trace(
    ox: float,
    oy: float,
    oz: float,
    dx: float,
    dy: float,
    dz: float,
    max_dist: float,
    walls: tuple[Box, ...],
    gx: float,
    gy: float,
    goal_visible: bool,
    config: SimConfig,
    strength: float,
    light: float,
) -> tuple[int, int, int]:
    best_t = max_dist
    kind = "sky"
    hx = hy = hz = 0.0
    if dz < -1e-6:
        t_floor = -oz / dz
        if 1e-4 < t_floor < best_t:
            px, py = ox + dx * t_floor, oy + dy * t_floor
            if 0.0 <= px <= config.world and 0.0 <= py <= config.world:
                best_t, kind, hx, hy, hz = t_floor, "floor", px, py, 0.0
    if dz > 1e-6:
        t_ceil = (config.wall_height + 0.4 - oz) / dz
        if 1e-4 < t_ceil < best_t:
            best_t, kind = t_ceil, "ceiling"
    for box in walls:
        t = ray_aabb_xy(ox, oy, dx, dy, box)
        if t is None or t >= best_t:
            continue
        z = oz + dz * t
        if 0.0 <= z <= config.wall_height:
            best_t, kind = t, "wall"
            hx, hy, hz = ox + dx * t, oy + dy * t, z
    if goal_visible:
        t = ray_circle_xy(ox, oy, dx, dy, gx, gy, 0.42)
        if t is not None and t < best_t:
            z = oz + dz * t
            if 0.0 <= z <= config.goal_height:
                best_t, kind = t, "goal"
                hx, hy, hz = ox + dx * t, oy + dy * t, z
    shade = max(0.25, min(1.15, light * (1.0 - 0.65 * best_t / max_dist)))
    return _albedo(kind, hx, hy, hz, strength, shade)


def _albedo(
    kind: str,
    x: float,
    y: float,
    z: float,
    strength: float,
    shade: float,
) -> tuple[int, int, int]:
    if kind == "sky":
        return _rgb(118, 168, 214, shade)
    if kind == "ceiling":
        return _rgb(90, 90, 96, shade)
    if kind == "goal":
        return _rgb(230, 44, 40, shade)
    if kind == "floor":
        check = (int(math.floor(x * 2.0)) + int(math.floor(y * 2.0))) & 1
        delta = int(36 * strength)
        base = 78
        v = base + (delta if check else -delta)
        return _rgb(v, v - 10, v - 18, shade)
    check = (int(math.floor(y * 3.0 + x * 3.0)) + int(math.floor(z * 4.0))) & 1
    delta = int(28 * strength)
    base = 118
    v = base + (delta if check else -delta)
    return _rgb(v, v, v + 6, shade)


def _rgb(r: int, g: int, b: int, shade: float) -> tuple[int, int, int]:
    return (
        int(min(255, max(0, r * shade))),
        int(min(255, max(0, g * shade))),
        int(min(255, max(0, b * shade))),
    )
