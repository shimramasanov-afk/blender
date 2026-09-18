from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.contracts import Observation, PreviousAction
from l2_brain.control.snn import LIFConfig, SNNController
from l2_brain.control.snn.plasticity import PlasticityConfig, RewardModulatedSTDP
from l2_brain.factory import build_encoder
from l2_brain.learning.reward import RewardEngine
from l2_brain.sim.config import catalog
from l2_brain.sim.environment import SimulationEnvironment


def frozen_spec(*, scenario: str, split: str, variant: int, seed: int):
    return next(
        item
        for item in catalog(seed, suite="frozen")
        if item.scenario == scenario and item.split == split and item.variant == variant
    )


def perturb_input_weights(controller: SNNController, *, noise: float, seed: int, w_max: float) -> None:
    rng = np.random.default_rng(seed)
    w = controller._net.w_in
    controller._net.w_in = np.clip(w + rng.normal(0.0, noise, w.shape), 0.0, w_max)


def run_learn_episode(
    spec,
    controller: SNNController,
    reward_engine: RewardEngine,
    *,
    learn: bool,
) -> dict[str, Any]:
    """One episode. Trainer reads GroundTruth; Observation stays sensor-only."""
    env = SimulationEnvironment(spec)
    enc = build_encoder("navigation_v1")
    env.initialize()
    enc.initialize()
    controller.reset_state()
    reward_engine.reset()
    view = env.reset_episode(spec)
    prev_gt = env._truth(contact=False, dropped=view.dropped, delayed=False)
    prev_obs: Observation | None = None
    rewards: list[float] = []
    success = env.reached_goal()
    ticks = 0
    collisions = 0
    try:
        for step_i in range(spec.config.max_steps):
            if success:
                break
            now = 1_000_000_000 + step_i * int(1_000_000_000 / spec.config.tick_hz)
            obs = enc.encode(view.frame, (), prev_obs, now, bool(view.dropped))
            _assert_no_privileged(obs)
            intent = controller.step(obs, now, 100_000_000)
            view, gt = env.step(intent)
            success = env.reached_goal()
            sample = reward_engine.step(prev_gt, gt, success=success)
            if learn:
                controller.apply_trainer_signal(sample.delivered)
            rewards.append(sample.delivered)
            collisions += int(gt.obstacle_contact)
            ticks += 1
            prev_gt = gt
            prev_obs = Observation(
                timestamp_ns=obs.timestamp_ns,
                frame_id=obs.frame_id,
                visual_features=obs.visual_features,
                target_bearing=obs.target_bearing,
                target_confidence=obs.target_confidence,
                motion_estimate=obs.motion_estimate,
                motion_confidence=obs.motion_confidence,
                telemetry=obs.telemetry,
                validity_mask=obs.validity_mask,
                previous_action=PreviousAction(
                    turn=intent.turn,
                    forward=intent.forward,
                    pulses=intent.pulses,
                ),
                navigation=obs.navigation,
            )
    finally:
        env.close()
        enc.close()
    return {
        "episode_id": spec.episode_id,
        "success": success,
        "ticks": ticks,
        "collisions": collisions,
        "reward_sum": float(sum(rewards)),
        "learned": learn,
        "privileged_in_observation": False,
    }


def _assert_no_privileged(obs: Observation) -> None:
    leaked = set(obs.__dataclass_fields__).intersection(
        {"agent_xy", "goal_xy", "distance_to_goal", "distance", "body_yaw", "walls"}
    )
    if leaked:
        raise RuntimeError(f"Observation leaked privileged fields: {leaked}")


def run_rstdp_series(
    *,
    scenario: str = "open_goal",
    split: str = "training",
    variant: int = 0,
    seed: int = 0,
    episodes: int = 8,
    noise: float = 0.35,
) -> dict[str, Any]:
    spec = frozen_spec(scenario=scenario, split=split, variant=variant, seed=seed)
    plastic_cfg = PlasticityConfig()
    control = _ready_snn(seed=seed, noise=noise, w_max=plastic_cfg.w_max)
    control_row = run_learn_episode(spec, control, RewardEngine(), learn=False)
    control.close()

    train = _ready_snn(seed=seed, noise=noise, w_max=plastic_cfg.w_max)
    plasticity = RewardModulatedSTDP(train.config.n, train.config.n_input, plastic_cfg)
    train.attach_plasticity(plasticity)
    plasticity.unfreeze()
    train_rows: list[dict[str, Any]] = []
    engine = RewardEngine()
    for _ in range(episodes):
        train_rows.append(run_learn_episode(spec, train, engine, learn=True))
    w_norm_after = float(np.linalg.norm(train._net.w_in))
    last_delta = float(plasticity.last_delta)
    plasticity.freeze()
    eval_row = run_learn_episode(spec, train, RewardEngine(), learn=False)
    train.close()
    return {
        "suite": "nav-sim-v1-mini",
        "hypothesis": "Noisy snn_core_v1 with 8 R-STDP episodes then freeze uses fewer ticks than the frozen noisy copy. Not Frozen 60. Not H3/H4.",
        "reject_if": "Eval ticks >= control ticks, NaN, crash, or Observation received GroundTruth.",
        "n_runs": 1,
        "why_one_run": "Hod 27 mini-set: one scene, one noise seed. Not a multi-seed claim.",
        "learned": True,
        "transfer_claim": False,
        "biological_claim": False,
        "control": control_row,
        "train": train_rows,
        "eval_frozen": eval_row,
        "w_in_norm_after": w_norm_after,
        "last_delta": last_delta,
        "improved": eval_row["ticks"] < control_row["ticks"],
    }


def export_rstdp_weights(
    *,
    seed: int = 0,
    episodes: int = 8,
    noise: float = 0.35,
) -> np.ndarray:
    """Replay hod27 recipe and return frozen w_in. Does not change snn_v1 defaults."""
    spec = frozen_spec(scenario="open_goal", split="training", variant=0, seed=seed)
    plastic_cfg = PlasticityConfig()
    train = _ready_snn(seed=seed, noise=noise, w_max=plastic_cfg.w_max)
    plasticity = RewardModulatedSTDP(train.config.n, train.config.n_input, plastic_cfg)
    train.attach_plasticity(plasticity)
    plasticity.unfreeze()
    engine = RewardEngine()
    for _ in range(episodes):
        run_learn_episode(spec, train, engine, learn=True)
    plasticity.freeze()
    weights = train._net.w_in.copy()
    train.close()
    return weights


def _ready_snn(*, seed: int, noise: float, w_max: float) -> SNNController:
    ctl = SNNController(LIFConfig(seed=seed))
    ctl.initialize()
    if noise > 0.0:
        perturb_input_weights(ctl, noise=noise, seed=seed + 17, w_max=w_max)
    return ctl


def write_learn_report(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
