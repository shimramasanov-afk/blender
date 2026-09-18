from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from l2_brain.control.ablation import CHANNEL_SETS

ChannelSet = Literal["target", "target_flow", "target_expansion", "all"]


@dataclass(frozen=True, slots=True)
class BaselineConfig:
    """All policy coefficients. No scene names, no learned weights."""

    k_attract: float = 1.6
    target_min_conf: float = 0.12
    bearing_align: float = 0.75
    cruise: float = 0.62
    search_forward: float = 0.18
    k_brake: float = 0.85
    k_avoid: float = 1.35
    k_unknown: float = 0.35
    k_expansion: float = 0.9
    k_center: float = 0.8
    k_residual: float = 0.25
    risk_choose: float = 0.22
    k_memory: float = 0.55
    side_hold_ticks: int = 12
    history_len: int = 8
    k_turn_persist: float = 0.25
    w_expansion: float = 0.5
    w_mass: float = 0.35
    w_body: float = 0.15
    stall_progress: float = 0.02
    stall_ticks: int = 8
    k_stall_avoid: float = 0.3
    k_search: float = 0.45
    bearing_hold_ticks: int = 10
    bearing_decay: float = 0.92
    unobs_decay: float = 0.985
    cmd_yaw_scale: float = 0.18
    cmd_yaw_trust: float = 0.70
    search_conf: float = 0.08
    track_hold_conf: float = 0.08
    aligned_avoid: float = 0.55
    fov_rad: float = 1.2
    recovery: bool = True
    progress_ema: float = 0.35
    evidence_inc: float = 0.14
    evidence_dec: float = 0.10
    evidence_stuck: float = 0.62
    evidence_min_ticks: int = 10
    scene_repeat: float = 0.94
    cmd_forward_min: float = 0.18
    recovery_hold_ticks: int = 16
    recovery_turn: float = 0.90
    recovery_crawl: float = 0.28
    recovery_backoff_ticks: int = 4
    attempt_memory: int = 4
    goal_mass: float = 0.10
    goal_bearing: float = 0.18
    structure_min: float = 0.14
    recover_max_retries: int = 3
    recover_cooldown_ticks: int = 16
    course_lock_bearing: float = 0.22
    course_lock_ticks: int = 4
    course_lock_forward: float = 0.72
    course_lock_turn: float = 0.0
    course_lock_track: float = 0.16
    hold_break_expansion: float = 0.08
    side_bias_ticks: int = 20
    skirt_forward: float = 0.55
    skirt_turn: float = 0.45
    peel_ticks: int = 40
    min_peel_ticks: int = 26
    peel_forward: float = 0.20
    search_peel_forward: float = 0.0
    slide_turn: float = 0.0
    front_block_steer: float = 0.18
    front_block_expansion: float = 0.03
    close_residual: float = 0.55
    front_block_streak: int = 2
    front_warmup_ticks: int = 1
    approach_forward: float = 0.50
    approach_turn: float = 0.0
    skirt_approach_ticks: int = 16
    unwind_ticks: int = 17
    max_contact_peel: int = 28
    approach_give_up: int = 55
    sidestep_ticks: int = 30
    restore_ticks: int = 13
    probe_forward: float = 0.45
    probe_gate_ticks: int = 14
    bypass_peel_ticks: int = 26
    probe_give_up_ticks: int = 55
    trap_peel_turn: float = 1.0
    slide_ticks: int = 22
    min_slide_ticks: int = 22
    max_slide_ticks: int = 85
    edge_reslide_ticks: int = 32
    align_ticks: int = 8
    hook_edge_ticks: int = 26
    hook_turn: float = 1.0
    hook_forward: float = 0.35
    wrap_turn: float = 0.85
    wrap_forward: float = 0.45
    wrap_ticks: int = 10
    wrap_exit_ticks: int = 20
    wrap_seek_ticks: int = 6
    wrap_exit_forward: float = 0.90
    hook_clear_ticks: int = 12
    hook_clear_forward: float = 0.90
    bypass_seek_forward: float = 0.68
    wrap_sprint_forward: float = 1.0
    wrap_sprint_bearing: float = 0.22
    wrap_clear_ticks: int = 8
    channels: ChannelSet = "all"

    def __post_init__(self) -> None:
        if self.history_len < 1 or self.side_hold_ticks < 1 or self.stall_ticks < 1:
            raise ValueError("hold/history windows must be >= 1")
        if self.fov_rad <= 0:
            raise ValueError("fov_rad must be positive")
        if not 0.0 <= self.cruise <= 1.0:
            raise ValueError("cruise must be in [0, 1]")
        if self.evidence_min_ticks < 2 or self.recovery_hold_ticks < 2:
            raise ValueError("recovery windows too short")
        if self.attempt_memory < 1 or self.recover_max_retries < 1 or self.recover_cooldown_ticks < 1:
            raise ValueError("attempt memory, retry limit and cooldown must be positive")
        if self.cmd_forward_min > self.search_forward:
            raise ValueError("cmd_forward_min must be <= search_forward so search counts as commanded motion")
        if not 0.0 < self.track_hold_conf <= self.target_min_conf:
            raise ValueError("track_hold_conf must be in (0, target_min_conf]")
        if self.course_lock_ticks < 1 or self.course_lock_bearing <= 0.0:
            raise ValueError("course lock window must be positive")
        if not 0.0 <= self.course_lock_forward <= 1.0 or not 0.0 <= self.course_lock_turn <= 1.0:
            raise ValueError("course lock forward/turn must be in [0, 1]")
        if not 0.0 < self.course_lock_track <= 1.0:
            raise ValueError("course_lock_track must be in (0, 1]")
        if self.hold_break_expansion < 0.0:
            raise ValueError("hold_break_expansion must be >= 0")
        if self.side_bias_ticks < 1 or self.peel_ticks < 1:
            raise ValueError("side_bias_ticks and peel_ticks must be >= 1")
        if self.min_peel_ticks < 1:
            raise ValueError("min_peel_ticks must be >= 1")
        if self.front_warmup_ticks < 1 or self.skirt_approach_ticks < 1 or self.unwind_ticks < 1:
            raise ValueError("front_warmup_ticks, skirt_approach_ticks and unwind_ticks must be >= 1")
        if self.front_block_streak < 1 or self.max_contact_peel < self.min_peel_ticks:
            raise ValueError("front_block_streak >= 1 and max_contact_peel >= min_peel_ticks")
        if self.approach_give_up < 1 or self.sidestep_ticks < 1 or self.restore_ticks < 1:
            raise ValueError("approach_give_up, sidestep_ticks and restore_ticks must be >= 1")
        if self.front_block_steer <= 0.0 or self.front_block_expansion < 0.0 or self.close_residual <= 0.0:
            raise ValueError("front block / close residual thresholds must be positive")
        if not 0.2 < self.skirt_forward <= 1.0 or not 0.0 < self.skirt_turn <= 1.0:
            raise ValueError("skirt_forward must be > 0.2 and skirt_turn in (0, 1]")
        if not 0.2 < self.approach_forward <= 1.0 or not 0.0 <= self.approach_turn <= 1.0:
            raise ValueError("approach_forward must be > 0.2 and approach_turn in [0, 1]")
        if not 0.2 < self.probe_forward <= 1.0:
            raise ValueError("probe_forward must be > 0.2")
        if self.probe_gate_ticks < 1 or self.bypass_peel_ticks < 1 or self.probe_give_up_ticks < 1:
            raise ValueError("probe_gate_ticks, bypass_peel_ticks and probe_give_up_ticks must be >= 1")
        if self.slide_ticks < 1:
            raise ValueError("slide_ticks must be >= 1")
        if self.min_slide_ticks < 1 or self.max_slide_ticks < self.min_slide_ticks:
            raise ValueError("min_slide_ticks >= 1 and max_slide_ticks >= min_slide_ticks")
        if self.edge_reslide_ticks < 1 or self.align_ticks < 1 or self.hook_edge_ticks < 1:
            raise ValueError("edge_reslide_ticks, align_ticks and hook_edge_ticks must be >= 1")
        if not 0.0 < self.trap_peel_turn <= 1.0:
            raise ValueError("trap_peel_turn must be in (0, 1]")
        if not 0.0 < self.hook_forward <= 1.0:
            raise ValueError("hook_forward must be in (0, 1]")
        if not 0.0 < self.hook_turn <= 1.0:
            raise ValueError("hook_turn must be in (0, 1]")
        if not 0.0 < self.wrap_turn <= 1.0:
            raise ValueError("wrap_turn must be in (0, 1]")
        if not 0.0 < self.wrap_forward <= 1.0:
            raise ValueError("wrap_forward must be in (0, 1]")
        if self.wrap_ticks < 1:
            raise ValueError("wrap_ticks must be >= 1")
        if self.wrap_exit_ticks < 1 or self.wrap_seek_ticks < 1:
            raise ValueError("wrap_exit_ticks and wrap_seek_ticks must be >= 1")
        if not 0.0 < self.wrap_exit_forward <= 1.0:
            raise ValueError("wrap_exit_forward must be in (0, 1]")
        if self.hook_clear_ticks < 1:
            raise ValueError("hook_clear_ticks must be >= 1")
        if not 0.0 < self.hook_clear_forward <= 1.0:
            raise ValueError("hook_clear_forward must be in (0, 1]")
        if not 0.0 < self.bypass_seek_forward <= 1.0:
            raise ValueError("bypass_seek_forward must be in (0, 1]")
        if not 0.0 < self.wrap_sprint_forward <= 1.0:
            raise ValueError("wrap_sprint_forward must be in (0, 1]")
        if self.wrap_sprint_bearing <= 0.0:
            raise ValueError("wrap_sprint_bearing must be positive")
        if self.wrap_clear_ticks < 1:
            raise ValueError("wrap_clear_ticks must be >= 1")
        if not 0.0 <= self.peel_forward <= 1.0 or not 0.0 <= self.search_peel_forward <= 1.0:
            raise ValueError("peel_forward/search_peel_forward must be in [0, 1]")
        if not 0.0 <= self.slide_turn <= 1.0:
            raise ValueError("slide_turn must be in [0, 1]")
        if self.channels not in CHANNEL_SETS:
            raise ValueError(f"channels must be one of {CHANNEL_SETS}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
