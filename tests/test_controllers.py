from __future__ import annotations

import numpy as np

from l2_brain.controllers import REGISTRY, make_controller
from l2_brain.features import extract
from l2_brain.types import Action, Observation


def _frame_with_blob(side: str) -> Observation:
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    frame[:] = (80, 80, 90)
    if side == "left":
        frame[16:48, 4:18] = (220, 36, 36)
    elif side == "right":
        frame[16:48, 46:60] = (220, 36, 36)
    elif side == "center":
        frame[16:48, 26:38] = (220, 36, 36)
    return Observation(frame=frame, timestamp_ns=0, tick=0)


def test_all_controllers_emit_bounded_actions() -> None:
    obs = _frame_with_blob("center")
    for name in REGISTRY:
        ctl = make_controller(name)
        ctl.reset()
        action = ctl.step(obs).clipped()
        assert isinstance(action, Action)
        assert -1.0 <= action.turn <= 1.0
        assert 0.0 <= action.forward <= 1.0
        assert 0.0 <= action.engage <= 1.0


def test_features_see_left_blob() -> None:
    feat = extract(_frame_with_blob("left"))
    assert feat.seen
    assert feat.centroid is not None
    assert feat.centroid < 0.4
    assert feat.left > feat.right


def test_reactive_turns_toward_left() -> None:
    action = make_controller("reactive").step(_frame_with_blob("left"))
    assert action.turn < 0


def test_recurrent_remembers_left_after_blank() -> None:
    ctl = make_controller("recurrent")
    ctl.reset()
    for _ in range(4):
        ctl.step(_frame_with_blob("left"))
    blank = Observation(frame=np.zeros((64, 64, 3), dtype=np.uint8), timestamp_ns=1, tick=5)
    action = ctl.step(blank)
    assert action.turn < 0


def test_reactive_forgets_on_blank() -> None:
    ctl = make_controller("reactive")
    ctl.step(_frame_with_blob("left"))
    blank = Observation(frame=np.zeros((64, 64, 3), dtype=np.uint8), timestamp_ns=1, tick=5)
    action = ctl.step(blank)
    assert action.turn > 0
