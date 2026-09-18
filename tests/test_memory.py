from __future__ import annotations

from dataclasses import replace

from l2_brain.contracts import PreviousAction
from l2_brain.control.baseline import BaselineController
from l2_brain.control.config import BaselineConfig
from l2_brain.control.eval import score_recovery
from l2_brain.control.memory import classify_situation
from l2_brain.vision.channels import MotionHypothesis

from test_baseline import _nav, _obs


def test_low_flow_alone_is_not_stuck() -> None:
    cfg = BaselineConfig(recovery=True, evidence_min_ticks=4)
    ctl = BaselineController(cfg)
    ctl.initialize()
    nav = replace(_nav(expansion=0.0), motion_confidence=0.0, hypothesis=MotionHypothesis(0.0, 0.0, 0.0, False, True, "low_confidence"))
    for i in range(8):
        ctl.step(_obs(bearing=0.2, conf=0.8, navigation=nav), 10 + i, 100)
    assert ctl.memory.situation != "blocked"
    assert ctl.last_diag is not None
    assert not ctl.last_diag.recovering
    ctl.close()


def test_forward_no_progress_repeat_triggers_recovery() -> None:
    cfg = BaselineConfig(recovery=True, evidence_min_ticks=4, evidence_inc=0.25, scene_repeat=0.5)
    ctl = BaselineController(cfg)
    ctl.initialize()
    nav = replace(_nav(center_d=0.2, expansion=0.0), duplicate_frame=True)
    prior = PreviousAction(turn=0.0, forward=0.7, pulses=())
    for i in range(12):
        ctl.step(_obs(bearing=0.40, conf=0.2, navigation=nav, previous=prior), 10 + i, 100)
    assert ctl.memory.situation == "blocked" or ctl.memory.recovering
    assert ctl.last_diag is not None
    assert ctl.last_diag.reason == "recover" or ctl.last_diag.no_progress_evidence >= cfg.evidence_stuck
    ctl.close()


def test_camera_turn_is_not_blocked() -> None:
    cfg = BaselineConfig(recovery=True, evidence_min_ticks=3, evidence_inc=0.4)
    ctl = BaselineController(cfg)
    ctl.initialize()
    nav = replace(
        _nav(expansion=0.0),
        duplicate_frame=True,
        hypothesis=MotionHypothesis(2.0, 0.0, 0.1, False, True, "camera_turn"),
    )
    prior = PreviousAction(turn=0.8, forward=0.05, pulses=())
    for i in range(10):
        ctl.step(_obs(bearing=0.1, conf=0.3, navigation=nav, previous=prior), 10 + i, 100)
    assert ctl.memory.situation == "camera_turn"
    assert not ctl.memory.recovering
    ctl.close()


def test_goal_like_is_not_recovery() -> None:
    sit = classify_situation(
        _obs(bearing=0.0, conf=0.9, mass=0.2),
        PreviousAction(0.0, 0.5, ()),
        None,
        0.0,
        mass=0.2,
        bearing_norm=0.0,
        conf=0.9,
        cfg=BaselineConfig(),
    )
    assert sit == "goal_like"


def test_failed_attempt_changes_sign() -> None:
    cfg = BaselineConfig(recovery=True, evidence_min_ticks=3, evidence_inc=0.35, recovery_hold_ticks=4, recovery_backoff_ticks=1)
    ctl = BaselineController(cfg)
    ctl.initialize()
    nav = replace(_nav(center_d=0.3, expansion=0.0), duplicate_frame=True)
    prior = PreviousAction(turn=0.0, forward=0.8, pulses=())
    signs = []
    for i in range(20):
        ctl.step(_obs(bearing=0.40, conf=0.15, navigation=nav, previous=prior), 10 + i, 100)
        if ctl.memory.recovering:
            signs.append(ctl.memory.recover_sign)
    assert len(set(signs)) >= 2
    ctl.close()


def test_memory_has_required_states() -> None:
    ctl = BaselineController()
    ctl.initialize()
    data = ctl.memory.to_dict()
    for key in (
        "last_bearing",
        "side",
        "progress_conf",
        "no_progress_evidence",
        "attempts",
    ):
        assert key in data
    ctl.close()


def test_recovery_scorer_separates_true_and_false() -> None:
    traces = []
    for i in range(12):
        traces.append(
            {
                "dist": 5.0,
                "x": 3.0,
                "y": 8.0,
                "contact": True,
                "cmd_forward": 0.6,
                "recovering": i == 8,
                "situation": "blocked" if i == 8 else "move",
                "evidence": 0.8,
            }
        )
    for i in range(8):
        traces.append(
            {
                "dist": 4.4 - i * 0.1,
                "x": 3.2 + i * 0.1,
                "y": 8.0,
                "contact": False,
                "cmd_forward": 0.5,
                "recovering": False,
                "situation": "move",
                "evidence": 0.1,
            }
        )
    scored = score_recovery(traces)
    assert scored["gt_stuck_windows"] >= 1
    assert scored["true_positives"] >= 1
    assert scored["recoveries"] == 1
    assert scored["recovery_successes"] == 1


def test_course_lock_transit_does_not_start_recovery() -> None:
    cfg = BaselineConfig(recovery=True, evidence_min_ticks=4, evidence_inc=0.25, scene_repeat=0.5)
    ctl = BaselineController(cfg)
    ctl.initialize()
    nav = replace(_nav(center_d=0.2, expansion=0.0), duplicate_frame=True)
    prior = PreviousAction(turn=0.0, forward=0.7, pulses=())
    for i in range(12):
        ctl.step(_obs(bearing=0.0, conf=0.2, navigation=nav, previous=prior), 10 + i, 100)
    assert ctl._course_locked
    assert not ctl.memory.recovering
    assert ctl.last_diag is not None
    assert ctl.last_diag.reason != "recover"
    ctl.close()


def test_empty_scene_repeat_is_not_blocked() -> None:
    cfg = BaselineConfig(recovery=True, evidence_min_ticks=4, evidence_inc=0.25, scene_repeat=0.5)
    ctl = BaselineController(cfg)
    ctl.initialize()
    nav = replace(_nav(expansion=0.0), duplicate_frame=True)
    prior = PreviousAction(turn=0.0, forward=0.7, pulses=())
    for i in range(12):
        ctl.step(_obs(bearing=0.0, conf=0.2, navigation=nav, previous=prior), 10 + i, 100)
    assert ctl.memory.situation != "blocked"
    assert ctl.last_diag is not None
    assert not ctl.last_diag.recovering
    ctl.close()


def test_no_xy_in_memory_module() -> None:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "src/l2_brain/control/memory.py").read_text(encoding="utf-8")
    assert "agent_xy" not in text
    assert "goal_xy" not in text
    assert "waypoint" not in text
