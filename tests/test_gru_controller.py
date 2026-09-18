from __future__ import annotations

import numpy as np

from l2_brain.contracts import EncodedVisual, Observation, ValidityMask
from l2_brain.control.gru import GRUConfig, GRUController


def _obs(*, bearing: float = 0.2, conf: float = 0.5) -> Observation:
    return Observation(
        timestamp_ns=1,
        frame_id=1,
        visual_features=EncodedVisual(0.0, 0.04, 0.0, 0.6, 0.04, conf),
        target_bearing=bearing,
        target_confidence=conf,
        motion_estimate=None,
        motion_confidence=0.0,
        telemetry=(),
        validity_mask=ValidityMask(True, True, True, False, True, False, False),
        previous_action=None,
        navigation=None,
    )


def test_hidden_state_persists_when_memory_on() -> None:
    ctl = GRUController(GRUConfig(hidden=16, with_memory=True, seed=1))
    ctl.initialize()
    first = ctl.hidden.copy()
    ctl.step(_obs(), 10, 100)
    mid = ctl.hidden.copy()
    ctl.step(_obs(bearing=0.3), 11, 100)
    assert not np.array_equal(first, mid)
    assert not np.array_equal(mid, ctl.hidden)
    ctl.close()


def test_hidden_resets_each_tick_without_memory() -> None:
    ctl = GRUController(GRUConfig(hidden=16, with_memory=False, seed=1))
    ctl.initialize()
    ctl.step(_obs(), 10, 100)
    assert np.allclose(ctl.hidden, 0.0)
    again = ctl.step(_obs(), 11, 100)
    third = ctl.step(_obs(), 12, 100)
    assert again.turn == third.turn
    assert again.forward == third.forward
    ctl.close()


def test_extreme_input_stays_finite() -> None:
    ctl = GRUController(GRUConfig(seed=2))
    ctl.initialize()
    intent = ctl.step(_obs(bearing=8.0, conf=1.0e6), 10, 100)
    assert np.isfinite(intent.turn)
    assert np.isfinite(intent.forward)
    assert np.isfinite(ctl.hidden).all()
    ctl.close()


def test_n_params_matches_dense_layout() -> None:
    ctl = GRUController(GRUConfig(hidden=16, n_in=6))
    assert ctl.n_params() == 1186


def test_stale_stops() -> None:
    ctl = GRUController()
    ctl.initialize()
    obs = _obs()
    stale = Observation(
        timestamp_ns=obs.timestamp_ns,
        frame_id=obs.frame_id,
        visual_features=obs.visual_features,
        target_bearing=obs.target_bearing,
        target_confidence=obs.target_confidence,
        motion_estimate=None,
        motion_confidence=0.0,
        telemetry=(),
        validity_mask=ValidityMask(True, True, True, False, True, False, True),
        previous_action=None,
    )
    intent = ctl.step(stale, 10, 100)
    assert intent.stop == "fire"
    assert intent.forward == 0.0
    ctl.close()
