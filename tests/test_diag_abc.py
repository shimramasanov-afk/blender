from __future__ import annotations

from l2_brain.contracts import EncodedVisual, Observation, ValidityMask
from l2_brain.control.diag_abc import apply_privileged
from l2_brain.sim.views import GroundTruth


def _obs() -> Observation:
    return Observation(
        timestamp_ns=1,
        frame_id=1,
        visual_features=EncodedVisual(0, 0, 0, None, 0, 0),
        target_bearing=None,
        target_confidence=0.0,
        motion_estimate=None,
        motion_confidence=0.0,
        telemetry=(),
        validity_mask=ValidityMask(True, True, False, False, True, False, False),
        previous_action=None,
    )


def test_hidden_goal_is_not_injected() -> None:
    gt = GroundTruth(
        tick=1,
        agent_xy=(3.4, 8.0),
        body_yaw=0.0,
        camera_yaw=0.0,
        goal_xy=(10.0, 8.0),
        distance_to_goal=6.6,
        obstacle_contact=False,
        goal_visible=False,
        dropped_frame=False,
        action_delayed=False,
        walls=(),
    )
    out = apply_privileged(_obs(), gt, 1.2)
    assert out.target_bearing is None
    assert out.target_confidence == 0.0
    assert not out.validity_mask.target


def test_visible_open_goal_is_injected() -> None:
    gt = GroundTruth(
        tick=1,
        agent_xy=(3.4, 8.0),
        body_yaw=0.0,
        camera_yaw=0.0,
        goal_xy=(10.0, 8.0),
        distance_to_goal=6.6,
        obstacle_contact=False,
        goal_visible=True,
        dropped_frame=False,
        action_delayed=False,
        walls=(),
    )
    out = apply_privileged(_obs(), gt, 1.2)
    assert out.target_confidence == 1.0
    assert out.target_bearing is not None
    assert out.validity_mask.target
