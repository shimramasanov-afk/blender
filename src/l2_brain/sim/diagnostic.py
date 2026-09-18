"""Scripted stand probes. Not autonomous navigation scores."""

from __future__ import annotations

from l2_brain.control.events import score_events
from l2_brain.contracts import MotorIntent
from l2_brain.sim.config import EpisodeSpec, SimConfig
from l2_brain.sim.environment import SimulationEnvironment, forward_intent
from l2_brain.sim.scenarios import layout_for
from l2_brain.sim.world import collides


def start_pose_legal(spec: EpisodeSpec) -> bool:
    layout = layout_for(spec)
    cfg = spec.config
    return not collides(layout.start_xy[0], layout.start_xy[1], layout.walls, cfg)


def goal_not_inside_wall(spec: EpisodeSpec) -> bool:
    layout = layout_for(spec)
    return not collides(layout.goal_xy[0], layout.goal_xy[1], layout.walls, spec.config)


def scripted_push_blockage(*, ticks: int = 20) -> dict:
    """Always command forward=1 into the wall. Detector check, not a policy score."""
    spec = EpisodeSpec("push_wall", "training", 0, 0, SimConfig(max_steps=ticks))
    env = SimulationEnvironment(spec)
    env.initialize()
    env.reset_episode(spec)
    traces: list[dict] = []
    try:
        for _ in range(ticks):
            intent = forward_intent()
            _view, gt = env.step(intent)
            traces.append(
                {
                    "dist": gt.distance_to_goal,
                    "x": gt.agent_xy[0],
                    "y": gt.agent_xy[1],
                    "cmd_forward": intent.forward,
                    "goal_visible": gt.goal_visible,
                    "in_fov": True,
                    "dropped": False,
                    "stale": False,
                    "reason": "seek",
                    "situation": "move",
                    "recovering": False,
                }
            )
    finally:
        env.close()
    events = score_events(traces, success=False, timeout=True, tick_hz=spec.config.tick_hz)
    return {
        "kind": "scripted_blockage",
        "not_autonomous_eval": True,
        "events": events,
        "physical_blockage": events["gt"]["physical_blockage"],
        "windows": events["gt"]["physical_blockage_windows"],
    }


def reverse_supported() -> bool:
    """Stand and MotorIntent v1 do not implement signed reverse."""
    sample = MotorIntent(
        turn=0.0,
        forward=-1.0,
        stop="idle",
        select_target="idle",
        attack="idle",
        confidence=1.0,
        valid_until_ns=1,
    ).clipped()
    return sample.forward < 0.0
