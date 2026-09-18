"""Privileged vision/control splits. Not an official visual-agent score."""

from __future__ import annotations

from dataclasses import replace

from l2_brain.contracts import MotorIntent, Observation, PreviousAction
from l2_brain.control.baseline import BaselineController, ControlDiagnostics
from l2_brain.control.config import BaselineConfig
from l2_brain.control.eval import _goal_rel, run_episode
from l2_brain.sim.config import EpisodeSpec
from l2_brain.sim.environment import SimulationEnvironment
from l2_brain.sim.observability import goal_observable
from l2_brain.sim.views import GroundTruth
from l2_brain.vision.encoder import NavigationEncoder


def apply_privileged(obs: Observation, gt: GroundTruth, fov_h: float) -> Observation:
    visible = obs.validity_mask.frame and not obs.validity_mask.stale and goal_observable(gt, fov_h)
    return replace(obs, target_bearing=float(-_goal_rel(gt)) if visible else None,
                   target_confidence=1.0 if visible else 0.0,
                   validity_mask=replace(obs.validity_mask, target=visible))


class OracleSeek:
    """Turn toward a visible bearing. No obstacle model. Diagnostic only."""

    name = "oracle_seek"

    def __init__(self) -> None:
        self._open = False
        self.last_diag = None

    def initialize(self) -> None:
        self._open = True

    def reset_state(self) -> None:
        self.last_diag = None

    def step(self, observation: Observation, now_ns: int, intent_ttl_ns: int) -> MotorIntent:
        if observation.validity_mask.stale or not observation.validity_mask.frame:
            return MotorIntent(0.0, 0.0, "fire", "idle", "idle", 0.0, now_ns + intent_ttl_ns).clipped()
        conf = observation.target_confidence
        bearing = observation.target_bearing
        if conf >= 0.12 and bearing is not None:
            turn = max(-1.0, min(1.0, 1.6 * (bearing / 0.6)))
            align = max(0.0, 1.0 - 0.75 * abs(bearing / 0.6))
            forward = 0.62 * align
        else:
            turn, forward = 0.45, 0.12
        self.last_diag = ControlDiagnostics(
            attract_turn=turn,
            avoid_turn=0.0,
            memory_turn=0.0,
            risk=0.0,
            progress=0.0,
            side=0.0,
            side_age=0,
            turn=turn,
            forward=forward,
            stop=False,
            reason="seek" if conf >= 0.12 else "search",
            target_confidence=conf,
        )
        return MotorIntent(turn, forward, "idle", "idle", "idle", max(conf, 0.15), now_ns + intent_ttl_ns).clipped()

    def close(self) -> None:
        self._open = False


def run_condition(spec: EpisodeSpec, condition: str) -> dict:
    """A: vision+baseline. B: privileged bearing+baseline. C: vision+oracle."""
    if condition == "A":
        row, result = run_episode(spec, config=BaselineConfig(recovery=False))
        return _pack(condition, False, row, result)
    if condition == "B":
        return _run_injected(spec, BaselineController(BaselineConfig(recovery=False)), privileged=True)
    if condition == "C":
        return _run_injected(spec, OracleSeek(), privileged=False)
    raise ValueError(condition)


def _pack(condition: str, privileged: bool, row, result) -> dict:
    return {
        "condition": condition,
        "privileged_diagnostic": privileged,
        "scenario": row.scenario,
        "success": row.success,
        "outcome": row.outcome,
        "cause": row.cause,
        "ticks": row.ticks,
        "collisions": row.collisions,
        "mean_target_conf": row.mean_target_conf,
        "vision_miss_rate": row.vision_miss_rate,
        "limitation": "privileged diagnostic; not official visual-agent score",
    }


def _run_injected(spec: EpisodeSpec, ctl, *, privileged: bool) -> dict:
    from l2_brain.control.eval import _summarize
    from l2_brain.experiment.clocks import mono_ns

    env = SimulationEnvironment(spec)
    enc = NavigationEncoder()
    env.initialize()
    ctl.initialize()
    enc.initialize()
    if hasattr(ctl, "reset_state"):
        ctl.reset_state()
    view = env.reset_episode(spec)
    prev = None
    truths = [env._truth(contact=False, dropped=view.dropped, delayed=False)]
    diags = []
    encodes = []
    infers = []
    confs: list[float] = []
    bearing_errs: list[float] = []
    traces = []
    stale_ticks = 0
    misses = 0
    in_fov = 0
    success = env.reached_goal()
    timeout = False
    try:
        from l2_brain.control.eval import _count_vision, _vision_sample

        for step_i in range(spec.config.max_steps):
            if success:
                break
            stale = bool(view.dropped)
            now = 1_000_000_000 + step_i * int(1_000_000_000 / spec.config.tick_hz)
            t0 = mono_ns()
            obs = enc.encode(view.frame, (), prev, now, stale)
            encodes.append((mono_ns() - t0) / 1_000_000.0)
            # last GT for inject: use current pose before step (from env)
            gt_now = env._truth(contact=False, dropped=stale, delayed=False)
            if privileged:
                obs = apply_privileged(obs, gt_now, spec.config.fov_h)
            _vision_sample(obs, gt_now, spec.config.fov_h, confs, bearing_errs)
            misses, in_fov = _count_vision(obs, gt_now, spec.config.fov_h, misses, in_fov)
            t1 = mono_ns()
            intent = ctl.step(obs, now, 100_000_000)
            infers.append((mono_ns() - t1) / 1_000_000.0)
            diag = getattr(ctl, "last_diag", None)
            if diag is not None:
                diags.append(diag)
                if getattr(diag, "stop", False):
                    stale_ticks += 1
            view, gt = env.step(intent)
            truths.append(gt)
            traces.append(
                {
                    "dist": gt.distance_to_goal,
                    "x": gt.agent_xy[0],
                    "y": gt.agent_xy[1],
                    "contact": gt.obstacle_contact,
                    "cmd_forward": intent.forward,
                    "applied_forward": (0.0 if env.last_applied_intent.stop == "fire"
                                        else env.last_applied_intent.forward),
                    "previous_x": gt_now.agent_xy[0],
                    "previous_y": gt_now.agent_xy[1],
                    "recovering": bool(getattr(diag, "recovering", False)),
                    "situation": getattr(diag, "situation", "move"),
                    "evidence": getattr(diag, "no_progress_evidence", 0.0),
                    "reason": getattr(diag, "reason", "seek"),
                    "goal_visible": gt_now.goal_visible,
                    "in_fov": goal_observable(gt_now, spec.config.fov_h),
                    "dropped": gt_now.dropped_frame,
                    "stale": stale,
                }
            )
            prev = Observation(
                timestamp_ns=obs.timestamp_ns,
                frame_id=obs.frame_id,
                visual_features=obs.visual_features,
                target_bearing=obs.target_bearing,
                target_confidence=obs.target_confidence,
                motion_estimate=obs.motion_estimate,
                motion_confidence=obs.motion_confidence,
                telemetry=obs.telemetry,
                validity_mask=obs.validity_mask,
                previous_action=PreviousAction(turn=intent.turn, forward=intent.forward, pulses=intent.pulses),
                navigation=obs.navigation,
            )
            success = env.reached_goal()
        else:
            timeout = not success
        result = env.result(success=success, timeout=timeout)
    finally:
        env.close()
        ctl.close()
        enc.close()
    row = _summarize(spec, result, truths, diags or [], encodes, infers, stale_ticks, confs, bearing_errs, misses, in_fov, traces)
    return _pack("B" if privileged else "C", privileged, row, result)
