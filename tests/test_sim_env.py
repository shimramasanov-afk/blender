from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from l2_brain.sim.config import SCENARIO_IDS, EpisodeSpec, SimConfig, catalog
from l2_brain.sim.environment import SimulationEnvironment, forward_intent, idle_intent, turn_intent
from l2_brain.sim.suite import assert_no_privileged_in_view, replay_intents, run_episode, write_results
from l2_brain.sim.views import AgentView, GroundTruth


def _spec(scenario: str = "open_goal", **cfg: object) -> EpisodeSpec:
    return EpisodeSpec(
        scenario=scenario,
        split="training",
        variant=0,
        seed=0,
        config=SimConfig(frame_w=32, frame_h=32, **{"max_steps": 40, **cfg}),  # type: ignore[arg-type]
    )


def test_same_seed_reproduces_frames_and_truth() -> None:
    spec = _spec()
    intents = [forward_intent(), turn_intent(0.4), forward_intent(), idle_intent()]
    a_views, a_gt = replay_intents(spec, intents)
    b_views, b_gt = replay_intents(spec, intents)
    assert [g.agent_xy for g in a_gt] == [g.agent_xy for g in b_gt]
    assert [g.camera_yaw for g in a_gt] == [g.camera_yaw for g in b_gt]
    for av, bv in zip(a_views, b_views, strict=True):
        assert av.frame.timestamp_capture_ns == bv.frame.timestamp_capture_ns
        assert av.dropped == bv.dropped
        assert np.array_equal(av.frame.image, bv.frame.image)


def test_agent_view_has_no_privileged_state() -> None:
    env = SimulationEnvironment(_spec("single_obstacle"))
    view = env.reset_episode()
    assert_no_privileged_in_view(view)
    view, gt = env.step(forward_intent())
    env.close()
    assert_no_privileged_in_view(view)
    assert isinstance(gt, GroundTruth)
    assert hasattr(gt, "distance_to_goal")
    assert hasattr(gt, "walls")
    assert not hasattr(view, "distance_to_goal")
    assert not hasattr(view, "walls")
    assert "agent_xy" not in view.__dataclass_fields__


def test_all_scenarios_reset_and_step() -> None:
    for name in SCENARIO_IDS:
        spec = _spec(name)
        env = SimulationEnvironment(spec)
        view = env.reset_episode()
        assert view.frame.image is not None
        assert view.frame.image.shape == (32, 32, 3)
        view, gt = env.step(idle_intent())
        assert gt.tick == 1
        env.close()


def test_success_is_reaching_goal_not_a_pulse() -> None:
    spec = _spec(
        start_xy=(4.0, 8.0),
        start_yaw=0.0,
        goal_xy=(4.15, 8.0),
        goal_radius=0.2,
        max_speed=0.2,
    )
    result = run_episode(spec, lambda _view: forward_intent())
    assert result.success
    assert result.terminal == "success"
    assert result.transfer_claim is False
    assert "MMORPG" in result.limitation


def test_timeout_and_metrics_are_separate() -> None:
    spec = _spec(max_steps=3)
    result = run_episode(spec, lambda _view: idle_intent())
    assert not result.success
    assert result.timeout
    assert result.collisions == 0
    assert result.path_length == 0.0
    assert result.time_s == 3 / spec.config.tick_hz


def test_collision_stops_inside_wall() -> None:
    spec = _spec("single_obstacle", start_xy=(6.2, 8.0), start_yaw=0.0, max_speed=0.35)
    env = SimulationEnvironment(spec)
    env.reset_episode()
    _view, gt = env.step(forward_intent())
    env.close()
    assert gt.obstacle_contact
    x, y = gt.agent_xy
    for x0, y0, x1, y1 in gt.walls:
        assert not (x0 <= x <= x1 and y0 <= y <= y1)


def test_camera_spin_does_not_move_body() -> None:
    spec = _spec("camera_spin", start_xy=(5.0, 8.0), start_yaw=0.0)
    env = SimulationEnvironment(spec)
    env.reset_episode()
    start = None
    yaws = []
    for _ in range(4):
        _view, gt = env.step(turn_intent(1.0))
        if start is None:
            start = gt.agent_xy
        assert gt.agent_xy == start
        yaws.append(gt.camera_yaw)
    env.close()
    assert len(set(round(y, 5) for y in yaws)) > 1


def test_dropped_frame_changes_time_and_flags() -> None:
    spec = _spec("latency_drops")
    env = SimulationEnvironment(spec)
    env.reset_episode()
    dropped = None
    prev_ts = None
    for _ in range(6):
        view, gt = env.step(forward_intent())
        assert prev_ts is None or view.frame.timestamp_capture_ns > prev_ts
        prev_ts = view.frame.timestamp_capture_ns
        if view.dropped:
            dropped = view
            assert gt.dropped_frame
            assert int(view.frame.image.sum()) == 0
    env.close()
    assert dropped is not None
    assert dropped.action_delayed


def test_splits_do_not_share_episode_ids() -> None:
    specs = catalog(0, config=SimConfig(frame_w=16, frame_h=16))
    ids = [s.episode_id for s in specs]
    assert len(ids) == len(set(ids))
    assert {s.split for s in specs} == {"training", "validation", "held_out"}
    assert len(specs) == 12 * (3 + 1 + 1)


def test_suite_writes_machine_json(tmp_path: Path) -> None:
    spec = _spec(max_steps=2)
    result = run_episode(spec, lambda _view: idle_intent())
    out = tmp_path / "nav.json"
    write_results(out, [result])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["transfer_claim"] is False
    episode = payload["episodes"][0]
    assert episode["seed"] == 0
    assert "config" in episode
    assert episode["success"] is False
    assert "collisions" in episode
    assert "path_length" in episode
    assert "direction_changes" in episode
    assert isinstance(result, object)
    assert isinstance(AgentView, type)
