from __future__ import annotations

from l2_brain.controllers import make_controller
from l2_brain.env.synthetic import SyntheticEnv
from l2_brain.loop import ControlLoop, assert_observation_is_official
from l2_brain.types import Action


def test_open_field_reactive_succeeds() -> None:
    env = SyntheticEnv(scenario="open_field")
    report = ControlLoop(env, make_controller("reactive")).run_episode(seed=None)
    assert report.success
    assert not report.stuck
    assert report.ticks < 200


def test_open_field_jittered_seeds() -> None:
    env = SyntheticEnv(scenario="open_field")
    wins = 0
    for seed in range(8):
        wins += int(ControlLoop(env, make_controller("reactive")).run_episode(seed).success)
    assert wins >= 6


def test_observation_has_no_privileged_fields() -> None:
    env = SyntheticEnv(scenario="open_field")
    obs = env.reset()
    assert_observation_is_official(obs)
    assert not hasattr(obs, "agent_xy")
    assert obs.frame.shape == (64, 64, 3)
    assert obs.frame.dtype == "uint8"


def test_loop_splits_infer_and_full_tick() -> None:
    env = SyntheticEnv(scenario="open_field")
    report = ControlLoop(env, make_controller("reactive")).run_episode()
    assert report.infer_ms
    assert report.loop_ms
    assert all(loop + 1e-6 >= infer for infer, loop in zip(report.infer_ms, report.loop_ms, strict=True))


def test_frozen_controller_is_stuck() -> None:
    class Frozen:
        name = "frozen"

        def reset(self, seed=None) -> None:
            return None

        def step(self, observation) -> Action:
            return Action(0.0, 0.0, 0.0)

    env = SyntheticEnv(scenario="open_field")
    report = ControlLoop(env, Frozen()).run_episode()
    assert report.stuck
    assert report.stuck_reason == "frozen"
    assert not report.success


def test_memory_probe_recurrent_keeps_sign() -> None:
    env = SyntheticEnv(scenario="memory_probe")
    report = ControlLoop(env, make_controller("recurrent")).run_episode()
    assert report.success
