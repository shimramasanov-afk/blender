"""Evaluator-only observability. Does not feed the policy."""

from __future__ import annotations

import math
from typing import Any, Literal

from l2_brain.sim.config import EpisodeSpec, catalog
from l2_brain.sim.environment import SimulationEnvironment
from l2_brain.sim.views import GroundTruth
from l2_brain.sim.world import Box, ray_aabb_xy, wrap

TaskClass = Literal[
    "visible_goal",
    "brief_occlusion",
    "observed_then_hidden",
    "never_observed_from_start",
    "moves_out_of_view",
]


def goal_los(
    x: float,
    y: float,
    gx: float,
    gy: float,
    walls: tuple[Box, ...],
    *,
    radius: float = 0.42,
) -> bool:
    dx, dy = gx - x, gy - y
    dist = math.hypot(dx, dy)
    if dist <= radius:
        return True
    ux, uy = dx / dist, dy / dist
    for box in walls:
        hit = ray_aabb_xy(x, y, ux, uy, box)
        if hit is not None and hit < dist - radius:
            return False
    return True


def goal_in_fov(x: float, y: float, yaw: float, gx: float, gy: float, fov_h: float) -> bool:
    return abs(wrap(math.atan2(gy - y, gx - x) - yaw)) <= 0.5 * fov_h


def goal_observable(gt: GroundTruth, fov_h: float) -> bool:
    """Evaluator-only centre LOS/FOV approximation, not pixel segmentation."""
    return (
        gt.goal_visible and not gt.dropped_frame
        and goal_in_fov(*gt.agent_xy, gt.camera_yaw, *gt.goal_xy, fov_h)
        and goal_los(*gt.agent_xy, *gt.goal_xy, tuple(Box(*box) for box in gt.walls))
    )


def look_around_visible(spec: EpisodeSpec, *, n_yaw: int = 16) -> dict[str, Any]:
    env = SimulationEnvironment(spec)
    env.initialize()
    env.reset_episode(spec)
    walls = env._walls
    gx, gy = env._gx, env._gy
    x, y = env._x, env._y
    yaw0 = env._camera_yaw
    fov = spec.config.fov_h
    hidden_flag = not env._goal_visible
    start_los = (not hidden_flag) and goal_los(x, y, gx, gy, walls)
    start_in_fov = goal_in_fov(x, y, yaw0, gx, gy, fov)
    found = False
    for i in range(n_yaw):
        yaw = yaw0 + (2 * math.pi * i) / n_yaw
        if (not hidden_flag) and goal_in_fov(x, y, yaw, gx, gy, fov) and goal_los(x, y, gx, gy, walls):
            found = True
            break
    env.close()
    return {
        "start_los": start_los,
        "start_in_fov": start_in_fov,
        "start_observed": start_los and start_in_fov and not hidden_flag,
        "visible_after_turn_in_place": found,
        "layout_hides_goal": hidden_flag,
        "moves": spec.scenario == "moving_target",
        "requires_exploration": (not found) and not hidden_flag,
        "memory_of_bearing_applicable": found or start_los,
    }


def classify(info: dict[str, Any], spec: EpisodeSpec) -> TaskClass:
    if spec.scenario == "moving_target":
        return "moves_out_of_view"
    if spec.scenario == "vanishing_target":
        return "observed_then_hidden"
    if info["start_observed"]:
        return "visible_goal"
    if info["visible_after_turn_in_place"]:
        return "visible_goal"
    if not info["start_los"] and info["memory_of_bearing_applicable"] is False:
        return "never_observed_from_start"
    if not info["start_los"]:
        return "brief_occlusion"
    return "never_observed_from_start"


def report_catalog(seed: int = 0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in catalog(seed):
        info = look_around_visible(spec)
        rows.append(
            {
                "episode_id": spec.episode_id,
                "scenario": spec.scenario,
                "split": spec.split,
                "variant": spec.variant,
                "task_class": classify(info, spec),
                **info,
            }
        )
    return rows
