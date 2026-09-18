import numpy as np
import pytest

from l2_brain.capture.profile import WindowProfile
from l2_brain.contracts import PreviousAction
from l2_brain.control.baseline import BaselineController
from l2_brain.control.config import BaselineConfig
from l2_brain.control.eval import _count_vision, run_episode, score_recovery
from l2_brain.control.memory import start_recovery
from l2_brain.sim.config import EpisodeSpec, SimConfig
from l2_brain.sim.environment import SimulationEnvironment
from l2_brain.vision.bench import checker, make_frame
from l2_brain.vision.config import VisionConfig
from l2_brain.vision.encoder import NavigationEncoder
from test_baseline import _obs


def test_dropped_frame_does_not_seed_next_flow():
    enc = NavigationEncoder()
    enc.initialize()
    enc.encode(make_frame(checker(), 1), (), None, 1, False)
    enc.encode(make_frame(np.zeros_like(checker()), 2), (), None, 2, True)
    obs = enc.encode(make_frame(checker(), 3), (), None, 3, False)
    # Resume with a fresh temporal baseline, not motion from black to scenery.
    assert obs.motion_confidence == 0
    assert obs.navigation.lighting_change == 0
    assert not any(obs.navigation.near.d_pos)
    enc.close()


def test_target_detection_respects_hud_mask():
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[:12] = (230, 44, 40)
    profile = WindowProfile.from_mapping({
        "masks": [{"name": "hud", "norm_rect": [0, 0, 1, 0.25]}],
    })
    enc = NavigationEncoder(VisionConfig(profile=profile))
    enc.initialize()
    obs = enc.encode(make_frame(image, 1), (), None, 1, False)
    assert obs.target_bearing is None
    assert obs.target_confidence == 0
    enc.close()


def test_occluded_target_is_not_a_detector_miss():
    env = SimulationEnvironment(EpisodeSpec("single_obstacle", "training", 0, 0))
    env.reset_episode()
    gt = env._truth(contact=False, dropped=False, delayed=False)
    assert _count_vision(_obs(), gt, 1.2, 0, 0) == (0, 0)
    env.close()


def test_vision_scoring_uses_pose_of_encoded_frame():
    cfg = SimConfig(frame_w=16, frame_h=16, max_steps=1,
                    start_xy=(3, 8), goal_xy=(10, 8), start_yaw=0.2)

    class InitialBearingEncoder:
        def reset_episode(self, seed):
            pass

        def encode(self, frame, telemetry, previous, now, stale):
            return _obs(bearing=0.2, conf=1.0)

    row, _ = run_episode(EpisodeSpec("open_goal", "training", 0, 0, cfg),
                         encoder=InitialBearingEncoder())
    assert row.bearing_err_rad_p50 == pytest.approx(0)
    assert row.net_displacement > 0  # Includes the very first action.


def test_unmatched_recovery_is_false_positive_even_without_progress():
    traces = [dict(x=0, y=0, dist=5, cmd_forward=0, recovering=i == 12,
                   situation="stand") for i in range(20)]
    scored = score_recovery(traces)
    assert scored["gt_stuck_windows"] == 0
    assert scored["detections"] == 1
    assert scored["false_positives"] == 1


def test_late_detection_inside_long_blockage_is_true_positive():
    traces = [dict(x=0, y=0, dist=5, cmd_forward=0.6, recovering=i == 20,
                   situation="move") for i in range(35)]
    scored = score_recovery(traces)
    assert scored["gt_stuck_windows"] == 1
    assert scored["true_positives"] == 1
    assert scored["false_positives"] == 0


def test_recovery_retry_budget_rearms_after_cooldown():
    cfg = BaselineConfig(recover_max_retries=1, recover_cooldown_ticks=2,
                         recovery_hold_ticks=2)
    ctl = BaselineController(cfg)
    ctl.initialize()
    start_recovery(ctl.memory, cfg)
    ctl.memory.situation = "blocked"
    for _ in range(2):
        ctl._drive_recovery(cfg)
    assert ctl.memory.cooldown == 2
    for _ in range(3):
        ctl._drive_recovery(cfg)
    assert ctl.memory.recovering
    assert len(ctl.memory.attempts) <= cfg.attempt_memory
    ctl.close()


def test_stale_observation_ages_bearing_memory_and_stops():
    ctl = BaselineController()
    ctl.initialize()
    ctl.step(_obs(bearing=0.3, conf=0.8), 1, 10)
    initial = ctl.memory.last_bearing_conf
    action = PreviousAction(0.5, 0.0, ())
    intent = ctl.step(_obs(stale=True, previous=action), 2, 10)
    assert intent.stop == "fire"
    assert ctl.memory.last_bearing_conf < initial
    assert ctl.memory.last_bearing == 0.3 / 0.6
    ctl.close()


def test_recovery_time_is_seconds():
    traces = [dict(x=0, y=0, dist=5, cmd_forward=0.6, recovering=i == 8,
                   situation="move") for i in range(12)]
    traces.append(dict(x=0.5, y=0, dist=5, cmd_forward=0.6,
                       recovering=False, situation="move"))
    scored = score_recovery(traces, tick_hz=20)
    assert scored["recovery_time_p50"] == pytest.approx(4 / 20)


def test_repeated_detections_do_not_reuse_a_gt_event():
    traces = [dict(x=0, y=0, dist=5, cmd_forward=0.6,
                   recovering=i in (10, 20), situation="move") for i in range(30)]
    scored = score_recovery(traces)
    assert scored["detections"] == 2
    assert scored["true_positives"] == 1
    assert scored["false_positives"] == 1


def test_pending_motion_is_not_physical_blockage():
    from l2_brain.control.events import score_events

    traces = [dict(x=0, y=0, dist=5, cmd_forward=0.6, applied_forward=0,
                   recovering=False, situation="move") for _ in range(12)]
    assert score_recovery(traces)["gt_stuck_windows"] == 0
    assert not score_events(traces, success=False, timeout=True)["gt"]["physical_blockage"]
