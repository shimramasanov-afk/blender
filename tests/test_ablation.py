from __future__ import annotations

import pytest

from l2_brain.control.ablation import apply_channel_ablation
from l2_brain.control.config import BaselineConfig
from l2_brain.control.eval import run_episode, write_report
from l2_brain.factory import build_encoder
from l2_brain.sim.config import EpisodeSpec, SimConfig
from test_baseline import _nav, _obs


def test_target_keeps_bearing_and_drops_navigation() -> None:
    raw = _obs(bearing=0.3, conf=0.8, navigation=_nav(center_d=0.5, expansion=0.2))
    out = apply_channel_ablation(raw, "target")
    assert out.target_bearing == 0.3
    assert out.target_confidence == 0.8
    assert out.navigation is None
    assert out.motion_confidence == 0.0
    assert not out.validity_mask.motion


def test_flow_keeps_sectors_and_zeros_expansion() -> None:
    raw = _obs(bearing=0.1, conf=0.5, navigation=_nav(center_d=0.4, expansion=0.3))
    out = apply_channel_ablation(raw, "target_flow")
    assert out.navigation is not None
    assert out.navigation.expansion == 0.0
    assert out.navigation.near.expansion == 0.0
    assert out.navigation.hypothesis.body_forward_like == 0.0
    assert out.navigation.near.d_pos[2] == 0.4


def test_expansion_keeps_scale_and_zeros_flow() -> None:
    raw = _obs(bearing=0.1, conf=0.5, navigation=_nav(center_d=0.4, expansion=0.3))
    out = apply_channel_ablation(raw, "target_expansion")
    assert out.navigation is not None
    assert out.navigation.expansion == 0.3
    assert out.navigation.near.expansion == 0.3
    assert out.navigation.near.d_pos[2] == 0.0
    assert out.navigation.motion_confidence == 0.0
    assert out.navigation.hypothesis.residual_object_like == 0.0


def test_all_is_identity() -> None:
    raw = _obs(bearing=0.2, conf=0.7, navigation=_nav())
    assert apply_channel_ablation(raw, "all") is raw


def test_unknown_channel_set_fails() -> None:
    with pytest.raises(ValueError, match="unknown channel set"):
        apply_channel_ablation(_obs(), "blob")
    with pytest.raises(ValueError, match="channels"):
        BaselineConfig(channels="blob")  # type: ignore[arg-type]


def test_vision_metrics_use_raw_encoder_not_gate() -> None:
    spec = EpisodeSpec("open_goal", "training", 0, 0, SimConfig(max_steps=4))
    gated, _ = run_episode(spec, config=BaselineConfig(channels="target", recovery=False))
    assert gated.mean_target_conf > 0.0
    assert gated.vision_miss_rate == 0.0


def test_color_blob_catalog_step_runs() -> None:
    spec = EpisodeSpec("open_goal", "training", 0, 0, SimConfig(max_steps=3))
    enc = build_encoder("color_blob")
    enc.initialize()
    try:
        row, _ = run_episode(spec, config=BaselineConfig(recovery=False), encoder=enc)
    finally:
        enc.close()
    assert row.ticks <= 3
    assert row.transfer_claim is False


def test_write_report_keeps_encoder_and_hypothesis(tmp_path) -> None:
    spec = EpisodeSpec("open_goal", "training", 0, 0, SimConfig(max_steps=2))
    row, _ = run_episode(spec, config=BaselineConfig(recovery=False))
    payload = write_report(
        tmp_path / "out.json",
        [row],
        extras={
            "encoder_name": "color_blob",
            "hypothesis": "H15 probe",
            "reject_if": "delta < 0.15",
        },
    )
    assert payload["encoder"] == "color_blob"
    assert payload["hypothesis"] == "H15 probe"
    assert payload["reject_if"] == "delta < 0.15"
