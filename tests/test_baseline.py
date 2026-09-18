from __future__ import annotations

from pathlib import Path

from l2_brain.contracts import EncodedVisual, Observation, PreviousAction, PRIVILEGED_OBSERVATION_FIELDS, ValidityMask
from l2_brain.control.baseline import BaselineController
from l2_brain.control.config import BaselineConfig
from l2_brain.control.eval import _cause, _outcome
from l2_brain.sim.config import SCENARIO_IDS, EpisodeSpec, SimConfig
from l2_brain.sim.views import EpisodeResult
from l2_brain.vision.channels import MotionHypothesis, NavigationChannels, ScaleChannels


def test_stale_observation_stops() -> None:
    ctl = BaselineController()
    ctl.initialize()
    intent = ctl.step(_obs(stale=True, bearing=0.2, conf=0.9), 10, 100)
    assert intent.stop == "fire"
    assert intent.forward == 0.0
    assert ctl.last_diag is not None
    assert ctl.last_diag.stop
    assert ctl.last_diag.reason == "stale"
    ctl.close()


def test_diagnostics_have_four_components() -> None:
    ctl = BaselineController()
    ctl.initialize()
    ctl.step(_obs(bearing=0.4, conf=0.8, navigation=_nav(center_d=0.4, expansion=0.1)), 10, 100)
    diag = ctl.last_diag
    assert diag is not None
    assert {"attract_turn", "avoid_turn", "memory_turn", "turn", "forward"} <= diag.to_dict().keys()
    assert abs(diag.attract_turn) > 0.0
    ctl.close()


def test_coefficients_live_in_config() -> None:
    weak = BaselineController(BaselineConfig(k_attract=0.2))
    strong = BaselineController(BaselineConfig(k_attract=2.4))
    weak.initialize()
    strong.initialize()
    payload = _obs(bearing=0.5, conf=1.0)
    weak.step(payload, 10, 100)
    strong.step(payload, 10, 100)
    assert strong.last_diag is not None and weak.last_diag is not None
    assert abs(strong.last_diag.attract_turn) > abs(weak.last_diag.attract_turn)
    weak.close()
    strong.close()


def test_search_forward_counts_as_commanded_motion() -> None:
    cfg = BaselineConfig()
    assert cfg.cmd_forward_min <= cfg.search_forward
    try:
        BaselineConfig(cmd_forward_min=0.25, search_forward=0.18)
    except ValueError as exc:
        assert "search_forward" in str(exc)
    else:
        raise AssertionError("mismatched motion thresholds must fail")


def test_centered_blob_holds_below_acquire() -> None:
    cfg = BaselineConfig()
    assert cfg.track_hold_conf < cfg.target_min_conf
    ctl = BaselineController(cfg)
    ctl.initialize()
    ctl.step(_obs(bearing=0.0, conf=0.09), 10, 100)
    assert ctl.last_diag is not None
    assert ctl.last_diag.target_confidence >= 0.08
    assert ctl.last_diag.reason == "seek"
    ctl.close()


def test_offcenter_weak_blob_does_not_lower_acquire() -> None:
    ctl = BaselineController()
    ctl.initialize()
    ctl.step(_obs(bearing=0.5, conf=0.09), 10, 100)
    assert ctl.last_diag is not None
    assert ctl.last_diag.target_confidence == 0.0
    assert ctl.last_diag.reason == "search"
    ctl.close()


def test_spread_weak_blob_is_not_acquired() -> None:
    ctl = BaselineController()
    ctl.initialize()
    payload = _obs(bearing=0.0, conf=0.09, mass=0.012)
    spread = EncodedVisual(0.014, 0.013, 0.008, 0.42, 0.012, 0.09)
    payload = Observation(
        timestamp_ns=payload.timestamp_ns,
        frame_id=payload.frame_id,
        visual_features=spread,
        target_bearing=payload.target_bearing,
        target_confidence=payload.target_confidence,
        motion_estimate=payload.motion_estimate,
        motion_confidence=payload.motion_confidence,
        telemetry=payload.telemetry,
        validity_mask=payload.validity_mask,
        previous_action=payload.previous_action,
        navigation=payload.navigation,
    )
    ctl.step(payload, 10, 100)
    assert ctl.last_diag is not None
    assert ctl.last_diag.target_confidence == 0.0
    assert ctl.last_diag.reason == "search"
    ctl.close()


def test_stable_heading_commits_forward() -> None:
    cfg = BaselineConfig(course_lock_ticks=3, course_lock_bearing=0.25, course_lock_forward=0.72)
    ctl = BaselineController(cfg)
    ctl.initialize()
    payload = _obs(bearing=0.05, conf=0.4)
    for i in range(4):
        intent = ctl.step(payload, 10 + i, 100)
    assert intent.forward >= 0.70
    assert abs(intent.turn) < 0.15
    ctl.close()


def test_speed_is_not_always_full() -> None:
    ctl = BaselineController()
    ctl.initialize()
    ctl.step(_obs(bearing=0.0, conf=0.9, navigation=_nav(center_d=0.5, expansion=0.12)), 10, 100)
    assert ctl.last_diag is not None
    assert ctl.last_diag.forward < 1.0
    ctl.close()


def test_blind_search_locks_yaw_sign() -> None:
    cfg = BaselineConfig(recovery=False, stall_ticks=40)
    ctl = BaselineController(cfg)
    ctl.initialize()
    nav = _nav(center_d=0.12, expansion=0.0)
    prev = None
    for i in range(8):
        intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=nav, previous=prev), 10 + i, 100)
        assert intent.forward >= 0.40
        assert abs(intent.turn) <= 0.05
        prev = PreviousAction(intent.turn, intent.forward, ())
    assert ctl.memory.side != 0.0
    assert not ctl.memory.probe_done
    assert ctl.memory.probe_distance_ticks >= 8
    ctl.close()


def test_deep_probe_switches_to_slide() -> None:
    cfg = BaselineConfig(
        recovery=False,
        probe_gate_ticks=3,
        bypass_peel_ticks=3,
        front_warmup_ticks=1,
        slide_ticks=3,
        min_slide_ticks=3,
        max_slide_ticks=20,
        edge_reslide_ticks=4,
        align_ticks=2,
        hook_edge_ticks=1,
        hook_clear_ticks=4,
        wrap_ticks=4,
        wrap_exit_ticks=2,
        wrap_seek_ticks=2,
        wrap_clear_ticks=3,
    )
    ctl = BaselineController(cfg)
    ctl.initialize()
    clear = _nav(center_d=0.05, expansion=0.0)
    blocked = _nav(center_d=0.45, expansion=0.08)
    prev = None
    for i in range(4):
        intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=clear, previous=prev), 10 + i, 100)
        assert abs(intent.turn) <= 0.05
        assert intent.forward >= 0.40
        prev = PreviousAction(intent.turn, intent.forward, ())
    assert ctl.memory.probe_distance_ticks >= 3
    for i in range(4):
        intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=blocked, previous=prev), 20 + i, 100)
        assert abs(intent.turn) >= 0.40
        assert intent.forward <= 0.25
        assert not ctl.memory.shallow
        prev = PreviousAction(intent.turn, intent.forward, ())
    peel_sign = 1.0 if intent.turn > 0.0 else -1.0
    intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=blocked, previous=prev), 30, 100)
    assert intent.forward >= 0.50
    assert abs(intent.turn) <= 0.05
    assert ctl.memory.slide
    prev = PreviousAction(intent.turn, intent.forward, ())
    for i in range(cfg.min_slide_ticks):
        intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=clear, previous=prev), 40 + i, 100)
        if ctl.memory.slide_age < cfg.min_slide_ticks:
            assert abs(intent.turn) <= 0.05
            assert intent.forward >= 0.50
        prev = PreviousAction(intent.turn, intent.forward, ())
    intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=clear, previous=prev), 80, 100)
    assert ctl.memory.slide_age >= cfg.min_slide_ticks
    assert not ctl.memory.slide
    assert intent.turn * peel_sign < 0.0
    assert abs(intent.turn) >= 0.40
    assert 0.20 <= intent.forward <= 0.45
    wall = _nav(center_d=0.45, expansion=0.08)
    prev = PreviousAction(intent.turn, intent.forward, ())
    intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=wall, previous=prev), 81, 100)
    assert ctl.memory.edge_seen
    assert ctl.memory.aligning or ctl.memory.slide_hold > 0 or ctl.memory.slide
    assert intent.turn * peel_sign > 0.0 or abs(intent.turn) <= 0.05
    prev = PreviousAction(intent.turn, intent.forward, ())
    for i in range(cfg.align_ticks + cfg.edge_reslide_ticks + 1):
        intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=clear, previous=prev), 82 + i, 100)
        prev = PreviousAction(intent.turn, intent.forward, ())
    assert not ctl.memory.slide
    assert intent.turn * peel_sign < 0.0
    assert abs(intent.turn) >= 0.70
    assert 0.20 <= intent.forward <= 0.45
    for i in range(cfg.wrap_ticks - 1):
        intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=clear, previous=prev), 90 + i, 100)
        prev = PreviousAction(intent.turn, intent.forward, ())
        assert intent.turn * peel_sign < 0.0
    intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=clear, previous=prev), 96, 100)
    prev = PreviousAction(intent.turn, intent.forward, ())
    assert abs(intent.turn) <= 0.08
    assert intent.forward >= 0.55
    intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=clear, previous=prev), 97, 100)
    prev = PreviousAction(intent.turn, intent.forward, ())
    assert abs(intent.turn) <= 0.08
    for i in range(cfg.wrap_seek_ticks):
        intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=clear, previous=prev), 98 + i, 100)
        prev = PreviousAction(intent.turn, intent.forward, ())
        assert intent.turn * peel_sign < 0.0
        assert abs(intent.turn) >= 0.70
    intent = ctl.step(_obs(bearing=-0.4, conf=0.4, navigation=clear, previous=prev), 100, 100)
    assert ctl.memory.had_target
    assert ctl.memory.clear_left == cfg.wrap_clear_ticks - 1
    assert not ctl.memory.edge_seen
    assert ctl.memory.wrap_sprint
    assert intent.forward >= 0.50
    ctl.close()


def test_shallow_probe_peels_without_slide() -> None:
    cfg = BaselineConfig(recovery=False, peel_ticks=10, probe_gate_ticks=14, front_warmup_ticks=1)
    ctl = BaselineController(cfg)
    ctl.initialize()
    blocked = _nav(center_d=0.45, expansion=0.08)
    prev = None
    for i in range(10):
        intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=blocked, previous=prev), 10 + i, 100)
        if i == 0:
            prev = PreviousAction(intent.turn, intent.forward, ())
            continue
        assert abs(intent.turn) >= 0.40
        assert intent.forward <= 0.25
        assert ctl.memory.shallow
        assert not ctl.memory.slide
        prev = PreviousAction(intent.turn, intent.forward, ())
    ctl.close()


def test_lost_target_holds_course_not_peel() -> None:
    ctl = BaselineController(BaselineConfig(recovery=False))
    ctl.initialize()
    prev = None
    for i in range(5):
        intent = ctl.step(_obs(bearing=0.0, conf=0.4, previous=prev), 10 + i, 100)
        prev = PreviousAction(intent.turn, intent.forward, ())
    assert ctl.memory.had_target
    intent = ctl.step(_obs(bearing=None, conf=0.0, previous=prev), 20, 100)
    assert abs(intent.turn) <= 0.05
    assert intent.forward >= 0.60
    assert not ctl.memory.probe_done
    assert ctl.memory.peel_age == 0
    assert not ctl.memory.slide
    ctl.close()


def test_course_lock_survives_target_loss() -> None:
    cfg = BaselineConfig(recovery=False, course_lock_ticks=3, course_lock_bearing=0.25)
    ctl = BaselineController(cfg)
    ctl.initialize()
    prev = None
    for i in range(5):
        intent = ctl.step(_obs(bearing=0.05, conf=0.4, previous=prev), 10 + i, 100)
        prev = PreviousAction(intent.turn, intent.forward, ())
    assert ctl._course_locked
    intent = ctl.step(_obs(bearing=None, conf=0.0, previous=prev), 20, 100)
    assert ctl._course_locked
    assert abs(intent.turn) <= 0.05
    assert intent.forward >= 0.60
    ctl.close()


def test_live_off_axis_target_tracks_without_peel() -> None:
    cfg = BaselineConfig(recovery=False, course_lock_ticks=3, course_lock_bearing=0.22)
    ctl = BaselineController(cfg)
    ctl.initialize()
    prev = None
    for i in range(5):
        intent = ctl.step(_obs(bearing=0.05, conf=0.4, previous=prev), 10 + i, 100)
        prev = PreviousAction(intent.turn, intent.forward, ())
    assert ctl._course_locked
    intent = ctl.step(_obs(bearing=0.35, conf=0.4, previous=prev), 20, 100)
    assert intent.turn > 0.05
    assert abs(intent.turn) <= cfg.course_lock_track + 1e-9
    assert intent.forward >= 0.60
    assert not ctl.memory.probe_done
    assert ctl.memory.peel_age == 0
    ctl.close()


def test_live_aligned_target_does_not_start_bypass() -> None:
    ctl = BaselineController(BaselineConfig(recovery=False))
    ctl.initialize()
    looming = _nav(center_d=0.25, expansion=0.04)
    prev = None
    for i in range(6):
        intent = ctl.step(_obs(bearing=0.0, conf=0.35, navigation=looming, previous=prev), 10 + i, 100)
        prev = PreviousAction(intent.turn, intent.forward, ())
    assert ctl.memory.had_target
    assert not ctl.memory.probe_done
    assert not ctl.memory.slide
    assert ctl.last_diag is not None
    assert ctl.last_diag.reason != "search"
    ctl.close()


def test_visible_target_clears_peel() -> None:
    ctl = BaselineController(BaselineConfig(recovery=False))
    ctl.initialize()
    nav = _nav(center_d=0.12, expansion=0.0)
    ctl.step(_obs(bearing=None, conf=0.0, navigation=nav), 10, 100)
    assert ctl.memory.peel_age > 0
    ctl.step(_obs(bearing=0.0, conf=0.4, navigation=nav), 11, 100)
    assert ctl.memory.peel_age == 0
    assert ctl.memory.side_lock == 0
    assert ctl.memory.had_target
    ctl.close()


def test_side_bias_ignores_opposite_gradient_during_lock() -> None:
    cfg = BaselineConfig(side_bias_ticks=10)
    ctl = BaselineController(cfg)
    ctl.initialize()
    left = _nav(left_d=0.6, right_d=0.05, center_d=0.35, expansion=0.08)
    right = _nav(left_d=0.05, right_d=0.6, center_d=0.35, expansion=0.08)
    prev = None
    for i in range(3):
        intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=left, previous=prev), 10 + i, 100)
        prev = PreviousAction(intent.turn, intent.forward, ())
    locked = ctl.memory.side
    assert locked != 0.0
    for i in range(6):
        intent = ctl.step(_obs(bearing=None, conf=0.0, navigation=right, previous=prev), 20 + i, 100)
        prev = PreviousAction(intent.turn, intent.forward, ())
        assert (1 if intent.turn > 0.0 else -1) == (1 if locked > 0.0 else -1)
    assert ctl.memory.side == locked
    ctl.close()


def test_side_memory_persists() -> None:
    cfg = BaselineConfig(side_hold_ticks=4, risk_choose=0.05, k_avoid=1.0, k_memory=0.8)
    ctl = BaselineController(cfg)
    ctl.initialize()
    left_heavy = _obs(bearing=0.0, conf=0.2, navigation=_nav(left_d=0.6, right_d=0.05, center_d=0.4, expansion=0.08))
    for i in range(6):
        ctl.step(left_heavy, 10 + i, 100)
    side = ctl.last_diag.side if ctl.last_diag else 0.0
    assert side != 0.0
    flipped = _obs(bearing=0.0, conf=0.2, navigation=_nav(left_d=0.05, right_d=0.6, center_d=0.4, expansion=0.08))
    ctl.step(flipped, 20, 100)
    assert ctl.last_diag is not None
    assert ctl.last_diag.side == side
    ctl.close()


def test_no_privileged_fields() -> None:
    ctl = BaselineController()
    ctl.initialize()
    obs = _obs(bearing=0.1, conf=0.5)
    ctl.step(obs, 1, 10)
    assert PRIVILEGED_OBSERVATION_FIELDS.isdisjoint(obs.__dataclass_fields__)
    ctl.close()


def test_source_has_no_scenario_names() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "l2_brain" / "control"
    text = "".join((root / name).read_text(encoding="utf-8") for name in ("baseline.py", "config.py", "memory.py"))
    for name in SCENARIO_IDS:
        assert f'"{name}"' not in text
        assert f"'{name}'" not in text


def test_reset_state_keeps_config() -> None:
    cfg = BaselineConfig(k_attract=0.4)
    ctl = BaselineController(cfg)
    ctl.initialize()
    ctl.memory.side = 1.0
    ctl.reset_state()
    assert ctl.memory.side == 0.0
    assert ctl._config.k_attract == 0.4
    ctl.reset_weights()
    assert ctl._config is ctl._template
    ctl.close()


def test_command_history_is_not_a_measurement() -> None:
    ctl = BaselineController()
    ctl.initialize()
    prior = PreviousAction(turn=1.0, forward=1.0, pulses=())
    ctl.step(_obs(bearing=0.0, conf=0.8, previous=prior), 10, 100)
    assert ctl.last_diag is not None
    assert ctl.last_diag.command_is_not_measurement
    ctl.close()


def test_attribution_splits_vision_and_control() -> None:
    success = _result(success=True, timeout=False, collisions=0, no_progress=False, direction_changes=0, path=2.0)
    assert _outcome(success, net=2.0) == "success"
    stuck = _result(success=False, timeout=True, collisions=8, no_progress=True, direction_changes=1, path=0.2)
    assert _outcome(stuck, net=0.1) == "stuck"
    weave = _result(success=False, timeout=True, collisions=0, no_progress=False, direction_changes=12, path=6.0)
    assert _outcome(weave, net=0.4) == "oscillate"
    assert _cause(stuck, "stuck", [], misses=8, in_fov=10, bearing_errs=[0.6], stale_ticks=0) == "vision"
    assert _cause(stuck, "stuck", [], misses=1, in_fov=10, bearing_errs=[0.05], stale_ticks=0) == "control"


def test_short_open_goal_can_succeed() -> None:
    from l2_brain.control.eval import run_episode

    spec = EpisodeSpec(
        scenario="open_goal",
        split="training",
        variant=0,
        seed=0,
        config=SimConfig(
            frame_w=32,
            frame_h=32,
            max_steps=50,
            start_xy=(9.1, 8.0),
            start_yaw=0.0,
            goal_xy=(10.2, 8.0),
            max_speed=0.16,
            goal_radius=0.75,
        ),
    )
    row, result = run_episode(spec)
    assert result.transfer_claim is False
    assert row.outcome in {"success", "timeout", "stuck", "oscillate"}
    assert row.cause in {"none", "vision", "control", "mixed", "stale"}
    assert row.success == result.success


def _obs(
    *,
    bearing: float | None = None,
    conf: float = 0.0,
    stale: bool = False,
    navigation: NavigationChannels | None = None,
    previous: PreviousAction | None = None,
    mass: float = 0.04,
) -> Observation:
    centroid = None if bearing is None else 0.5 + bearing / 1.2
    return Observation(
        timestamp_ns=1,
        frame_id=1,
        visual_features=EncodedVisual(0.0, mass, 0.0, centroid, mass, conf),
        target_bearing=bearing,
        target_confidence=conf,
        motion_estimate=None,
        motion_confidence=0.0,
        telemetry=(),
        validity_mask=ValidityMask(
            frame=True,
            visual_features=True,
            target=bearing is not None and not stale,
            motion=False,
            telemetry=True,
            previous_action=previous is not None,
            stale=stale,
        ),
        previous_action=previous,
        navigation=navigation,
    )


def _nav(*, left_d: float = 0.0, right_d: float = 0.0, center_d: float = 0.0, expansion: float = 0.0) -> NavigationChannels:
    zeros = (0.0,) * 15
    d_pos = []
    for iy in range(3):
        for ix in range(5):
            if ix <= 1:
                d_pos.append(left_d)
            elif ix >= 3:
                d_pos.append(right_d)
            else:
                d_pos.append(center_d)
    contrast = tuple(0.1 + v for v in d_pos)
    scale = ScaleChannels(
        name="near",
        brightness=zeros,
        contrast=contrast,
        d_pos=tuple(d_pos),
        d_neg=zeros,
        flow_u=(0.0,) * 48,
        flow_v=(0.0,) * 48,
        expansion=expansion,
        motion_confidence=0.4,
        weak_texture_frac=0.1,
        valid_flow_frac=0.6,
    )
    return NavigationChannels(
        preprocess_ms=0.1,
        width=48,
        height=32,
        sectors_x=5,
        sectors_y=3,
        far=scale,
        near=scale,
        target_bearing=0.0,
        target_confidence=0.4,
        motion_confidence=0.4,
        expansion=expansion,
        flow_absent_is_not_clear=True,
        duplicate_frame=False,
        abrupt_cut=False,
        lighting_change=0.0,
        hypothesis=MotionHypothesis(0.0, max(0.0, expansion), 0.2, False, True, "uncertain"),
        no_object_model=True,
    )


def _result(
    *,
    success: bool,
    timeout: bool,
    collisions: int,
    no_progress: bool,
    direction_changes: int,
    path: float,
) -> EpisodeResult:
    return EpisodeResult(
        episode_id="t",
        scenario="open_goal",
        split="training",
        variant=0,
        seed=0,
        config={},
        success=success,
        timeout=timeout,
        collisions=collisions,
        no_progress=no_progress,
        path_length=path,
        time_s=1.0,
        direction_changes=direction_changes,
        ticks=20,
        terminal="success" if success else "timeout",
        transfer_claim=False,
        limitation="test",
    )
