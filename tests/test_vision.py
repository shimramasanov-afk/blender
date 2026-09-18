from __future__ import annotations

from pathlib import Path

import numpy as np

from l2_brain.capture.profile import WindowProfile
from l2_brain.contracts import PreviousAction, PRIVILEGED_OBSERVATION_FIELDS
from l2_brain.sim.config import EpisodeSpec, SimConfig
from l2_brain.sim.environment import SimulationEnvironment, forward_intent, turn_intent
from l2_brain.vision.bench import checker, discrimination_score, encode_pair, make_frame, measure_configs, pick_starter, shift, zoom
from l2_brain.vision.config import STARTER, VisionConfig
from l2_brain.vision.diagnose import write_ppm
from l2_brain.vision.encoder import NavigationEncoder


def test_static_scene_has_near_zero_motion() -> None:
    image = checker()
    ch = encode_pair(image, image.copy())
    assert ch.duplicate_frame or ch.motion_confidence < 0.25
    assert ch.hypothesis.label == "low_confidence" or abs(ch.expansion) < 0.2


def test_horizontal_shift_is_camera_like() -> None:
    ch = encode_pair(checker(), shift(checker(), 4))
    assert ch.motion_confidence > 0.2
    assert abs(sum(ch.far.flow_u) / max(len(ch.far.flow_u), 1)) > 0.8
    assert ch.hypothesis.label == "camera_turn"


def test_zoom_is_approach_like() -> None:
    ch = encode_pair(checker(), zoom(checker(), 1.14))
    assert ch.expansion > 0.04
    assert ch.hypothesis.label == "approach"
    assert ch.flow_absent_is_not_clear is True


def test_low_texture_is_not_a_clear_path() -> None:
    flat = np.full((64, 80, 3), 90, dtype=np.uint8)
    ch = encode_pair(flat, shift(flat, 4))
    assert ch.far.weak_texture_frac > 0.5
    assert ch.hypothesis.label == "low_confidence"
    assert ch.flow_absent_is_not_clear is True


def test_lighting_change_is_not_treated_as_flow() -> None:
    base = checker()
    bright = np.clip(base.astype(np.int16) + 50, 0, 255).astype(np.uint8)
    ch = encode_pair(base, bright)
    assert ch.lighting_change > 0.04
    assert ch.hypothesis.label in {"low_confidence", "uncertain"}
    assert abs(ch.expansion) < 0.05 or ch.motion_confidence < 0.3


def test_abrupt_cut_marks_low_confidence() -> None:
    other = checker(cell=3)
    other[:, :] = (20, 180, 200)
    ch = encode_pair(checker(), other)
    assert ch.abrupt_cut or ch.hypothesis.label == "low_confidence"
    assert ch.motion_confidence < 0.25 or ch.abrupt_cut


def test_duplicate_and_dropped_frame() -> None:
    enc = NavigationEncoder()
    enc.initialize()
    image = checker()
    enc.encode(make_frame(image, 1), (), None, 1, False)
    obs = enc.encode(make_frame(image, 1), (), None, 2, False)
    assert obs.validity_mask.duplicate
    assert obs.navigation.duplicate_frame  # type: ignore[union-attr]
    stale = enc.encode(make_frame(shift(image, 4), 3), (), None, 3, True)
    assert stale.validity_mask.stale
    assert stale.navigation.hypothesis.label == "low_confidence"  # type: ignore[union-attr]
    assert stale.navigation.expansion == 0.0  # type: ignore[union-attr]
    assert stale.motion_estimate is None
    resumed = enc.encode(make_frame(shift(image, 8), 4), (), None, 4, False)
    assert resumed.motion_estimate is None
    assert resumed.navigation.expansion == 0.0  # type: ignore[union-attr]
    assert resumed.navigation.hypothesis.label == "low_confidence"  # type: ignore[union-attr]
    enc.close()


def test_hud_mask_excludes_static_overlay() -> None:
    image = checker()
    image[:8, :] = (255, 255, 0)
    moved = shift(image, 4)
    moved[:8, :] = (255, 255, 0)
    profile = WindowProfile.from_mapping(
        {
            "profile_id": "test-hud",
            "roi": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            "masks": [{"name": "ui", "norm_rect": [0.0, 0.0, 1.0, 0.14]}],
        }
    )
    ch = encode_pair(image, moved, VisionConfig(profile=profile))
    assert ch.hypothesis.label == "camera_turn"


def test_command_is_not_treated_as_measurement() -> None:
    enc = NavigationEncoder()
    enc.initialize()
    first = enc.encode(make_frame(checker(), 1), (), None, 1, False)
    from dataclasses import replace

    prior = replace(first, previous_action=PreviousAction(turn=1.0, forward=1.0, pulses=()))
    second = enc.encode(make_frame(checker(), 2), (), prior, 2, False)
    hypo = second.navigation.hypothesis  # type: ignore[union-attr]
    assert hypo.command_prior_used
    assert hypo.command_is_not_measurement
    enc.close()


def test_no_privileged_fields() -> None:
    ch = encode_pair(checker(), shift(checker(), 3))
    assert PRIVILEGED_OBSERVATION_FIELDS.isdisjoint(ch.__dataclass_fields__)
    assert ch.no_object_model is True


def test_diagnostic_overlay_written(tmp_path: Path) -> None:
    enc = NavigationEncoder(VisionConfig(diagnose=True))
    enc.initialize()
    enc.encode(make_frame(checker(), 1), (), None, 1, False)
    enc.encode(make_frame(shift(checker(), 4), 2), (), None, 2, False)
    assert enc.last_diag is not None
    path = tmp_path / "flow.ppm"
    write_ppm(path, enc.last_diag)
    assert path.stat().st_size > 100
    enc.close()


def test_sim_turn_vs_approach() -> None:
    turn = _sim_pair("camera_spin", lambda: turn_intent(1.0), steps=2)
    approach = _sim_pair(
        "single_obstacle",
        lambda: forward_intent(),
        steps=2,
        start_xy=(5.2, 8.0),
        start_yaw=0.0,
    )
    assert turn.hypothesis.label in {"camera_turn", "uncertain"}
    assert approach.hypothesis.label in {"approach", "uncertain"}
    if turn.motion_confidence >= 0.22 and approach.motion_confidence >= 0.22:
        assert turn.hypothesis.camera_yaw_like > approach.hypothesis.camera_yaw_like * 0.6
        assert approach.expansion > turn.expansion


def test_starter_config_is_justified() -> None:
    rows = measure_configs(repeats=5)
    chosen = pick_starter(rows)
    disc = discrimination_score(STARTER)
    assert disc["accuracy"] >= 5 / 6
    assert chosen["width"] == STARTER.width
    assert chosen["height"] == STARTER.height
    assert chosen.get("sim_separates") is True
    assert any(row["width"] == STARTER.width and row["height"] == STARTER.height for row in rows)


def _sim_pair(scenario: str, intent_fn, *, steps: int, **cfg: object):
    spec = EpisodeSpec(
        scenario=scenario,
        split="training",
        variant=0,
        seed=0,
        config=SimConfig(frame_w=64, frame_h=64, **{"max_steps": 20, **cfg}),  # type: ignore[arg-type]
    )
    env = SimulationEnvironment(spec)
    env.initialize()
    view = env.reset_episode()
    enc = NavigationEncoder()
    enc.initialize()
    obs = enc.encode(_view_frame(view.frame.image, 1), (), None, 1, False)
    for i in range(steps):
        view, _gt = env.step(intent_fn())
        obs = enc.encode(_view_frame(view.frame.image, i + 2), (), obs, i + 2, False)
    env.close()
    enc.close()
    assert obs.navigation is not None
    return obs.navigation


def _view_frame(image: np.ndarray | None, frame_id: int):
    assert image is not None
    return make_frame(np.ascontiguousarray(image), frame_id)


def test_vectorized_flow_matches_loop() -> None:
    from l2_brain.vision.flow import reference_flow, reference_flow_loop

    cfg = VisionConfig()
    rng = np.random.default_rng(1)
    prev = rng.integers(0, 255, (32, 48), dtype=np.uint8)
    curr = np.roll(prev, 3, axis=1)
    curr = np.clip(curr.astype(np.int16) + rng.integers(-4, 5, curr.shape), 0, 255).astype(np.uint8)
    fast = reference_flow(prev, curr, cfg)
    slow = reference_flow_loop(prev, curr, cfg)
    assert np.array_equal(fast.u, slow.u)
    assert np.array_equal(fast.v, slow.v)
    assert np.array_equal(fast.weak_texture, slow.weak_texture)
    assert np.allclose(fast.confidence, slow.confidence, atol=1e-6)
