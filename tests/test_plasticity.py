from __future__ import annotations

import numpy as np

from l2_brain.contracts import EncodedVisual, Observation, ValidityMask
from l2_brain.control.snn.plasticity import PlasticityConfig, RewardModulatedSTDP, apply_dale
from l2_brain.learning.es import GaussianES
from l2_brain.learning.reward import RewardConfig, RewardEngine
from l2_brain.sim.views import GroundTruth


def _gt(dist: float, *, contact: bool = False, tick: int = 0) -> GroundTruth:
    return GroundTruth(
        tick=tick,
        agent_xy=(0.0, 0.0),
        body_yaw=0.0,
        camera_yaw=0.0,
        goal_xy=(dist, 0.0),
        distance_to_goal=dist,
        obstacle_contact=contact,
        goal_visible=True,
        dropped_frame=False,
        action_delayed=False,
        walls=(),
    )


def test_eligibility_decays_to_zero_without_spikes() -> None:
    rule = RewardModulatedSTDP(4, 3, PlasticityConfig())
    rule.unfreeze()
    rule.eligibility[:] = 1.0
    rule.decay_only(dt_ms=150.0, steps=20)
    assert float(np.max(np.abs(rule.eligibility))) < 1e-4


def test_positive_reward_strengthens_active_synapse() -> None:
    rule = RewardModulatedSTDP(2, 2, PlasticityConfig(eta=0.1, delta_max=0.5))
    rule.unfreeze()
    rule.observe(np.array([1.0, 0.0]), np.array([1.0, 0.0]), dt_ms=1.0)
    weights = np.ones((2, 2), dtype=np.float64)
    updated = rule.modulate(weights, 1.0)
    assert updated[0, 0] > weights[0, 0]
    assert np.isfinite(updated).all()


def test_negative_reward_weakens_active_synapse() -> None:
    rule = RewardModulatedSTDP(2, 2, PlasticityConfig(eta=0.1, delta_max=0.5))
    rule.unfreeze()
    rule.observe(np.array([1.0, 0.0]), np.array([1.0, 0.0]), dt_ms=1.0)
    weights = np.full((2, 2), 1.0)
    updated = rule.modulate(weights, -1.0)
    assert updated[0, 0] < weights[0, 0]
    assert updated[0, 0] >= 0.0


def test_zero_reward_leaves_weights() -> None:
    rule = RewardModulatedSTDP(2, 2)
    rule.unfreeze()
    rule.observe(np.array([1.0, 1.0]), np.array([1.0, 1.0]), dt_ms=1.0)
    weights = np.full((2, 2), 0.8)
    updated = rule.modulate(weights, 0.0)
    assert np.array_equal(updated, weights)


def test_dale_cannot_flip_excitatory_to_inhibitory() -> None:
    cfg = PlasticityConfig(eta=1.0, delta_max=5.0, w_max=2.0)
    rule = RewardModulatedSTDP(2, 2, cfg)
    rule.unfreeze()
    rule.eligibility[:] = 1.0
    updated = rule.modulate(np.full((2, 2), 0.4), -10.0)
    assert updated.min() >= 0.0
    rec = apply_dale(np.array([[0.5, -0.5], [0.2, -0.1]]), PlasticityConfig(mode="recurrent", n_e=1, w_max=2.0))
    assert rec[0, 0] >= 0.0
    assert rec[0, 1] <= 0.0
    assert rec[1, 1] <= 0.0


def test_freeze_blocks_observe_and_update() -> None:
    rule = RewardModulatedSTDP(2, 2, PlasticityConfig(eta=0.2))
    rule.freeze()
    before = rule.eligibility.copy()
    rule.observe(np.ones(2), np.ones(2), dt_ms=1.0)
    assert np.array_equal(rule.eligibility, before)
    weights = np.ones((2, 2))
    assert np.array_equal(rule.modulate(weights, 1.0), weights)


def test_checkpoint_roundtrip() -> None:
    rule = RewardModulatedSTDP(2, 3)
    rule.unfreeze()
    rule.eligibility[0, 1] = 0.4
    snap = rule.checkpoint(np.full((2, 3), 0.7))
    rule.reset_traces()
    restored = rule.restore(snap)
    assert restored[0, 0] == 0.7
    assert rule.eligibility[0, 1] == 0.4
    assert rule.frozen is False


def test_reward_progress_collision_goal_and_delay() -> None:
    engine = RewardEngine(RewardConfig(normalize=False, delay_ticks=1, stall_ticks=3))
    first = engine.step(_gt(2.0), _gt(1.8), success=False)
    assert first.progress_quanta >= 1
    assert first.delayed == 0.0
    second = engine.step(_gt(1.8), _gt(1.8, contact=True), success=False)
    assert second.collision
    assert second.delayed == first.raw
    terminal = engine.step(_gt(1.8, contact=True), _gt(0.1), success=True)
    assert terminal.goal
    assert terminal.raw >= 1.0


def test_reward_is_not_an_observation_field() -> None:
    obs = Observation(
        timestamp_ns=1,
        frame_id=1,
        visual_features=EncodedVisual(0.0, 0.0, 0.0, None, 0.0, 0.0),
        target_bearing=0.1,
        target_confidence=0.4,
        motion_estimate=None,
        motion_confidence=0.0,
        telemetry=(),
        validity_mask=ValidityMask(True, True, True, False, False, False, False),
        previous_action=None,
    )
    assert "distance_to_goal" not in obs.__dataclass_fields__
    assert "agent_xy" not in obs.__dataclass_fields__
    assert RewardEngine.source == "privileged_ground_truth"


def test_es_zero_reward_is_noop() -> None:
    es = GaussianES(4)
    es.unfreeze()
    params = np.zeros(4)
    noise = es.ask()
    assert np.array_equal(es.tell(params, noise, 0.0), params)
