from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Literal

from l2_brain.contracts import MotorIntent, Observation, PreviousAction
from l2_brain.control.config import BaselineConfig
from l2_brain.control.memory import (
    ShortTermMemory,
    classify_situation,
    finish_recovery,
    recovery_command,
    scene_similarity,
    scene_structure,
    scene_vector,
    start_recovery,
    update_evidence,
)
from l2_brain.vision.channels import NavigationChannels, ScaleChannels

Reason = Literal["stale", "seek", "avoid", "hold", "search", "recover"]


@dataclass(frozen=True, slots=True)
class ControlDiagnostics:
    attract_turn: float
    avoid_turn: float
    memory_turn: float
    risk: float
    progress: float
    side: float
    side_age: int
    turn: float
    forward: float
    stop: bool
    reason: Reason
    target_confidence: float
    situation: str = "move"
    progress_conf: float = 0.0
    no_progress_evidence: float = 0.0
    recovering: bool = False
    recover_age: int = 0
    scene_repeat_score: float = 0.0
    command_is_not_measurement: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaselineController:
    """Transparent non-learning policy. Sensors in, weighted sum out."""

    def __init__(self, config: BaselineConfig | None = None) -> None:
        self._template = config or BaselineConfig()
        self._config = self._template
        self.name = "baseline_memory_v1" if self._config.recovery else "baseline_v1"
        self._open = False
        self._side_age = 0
        self._history: deque[PreviousAction] = deque(maxlen=self._config.history_len)
        self._prev_mass = 0.0
        self._hold_age = 0
        self._stall = 0
        self._course_lock_age = 0
        self._course_locked = False
        self.memory = ShortTermMemory(attempts=deque(maxlen=self._config.attempt_memory))
        self.last_diag: ControlDiagnostics | None = None

    def initialize(self) -> None:
        self._open = True
        self.reset_state()

    def reset_state(self) -> None:
        self._side_age = 0
        self._history.clear()
        self._prev_mass = 0.0
        self._hold_age = 0
        self._stall = 0
        self._course_lock_age = 0
        self._course_locked = False
        self.memory = ShortTermMemory(attempts=deque(maxlen=self._config.attempt_memory))
        self.last_diag = None

    def reset_weights(self) -> None:
        self._config = self._template
        self.name = "baseline_memory_v1" if self._config.recovery else "baseline_v1"

    def step(self, observation: Observation, now_ns: int, intent_ttl_ns: int) -> MotorIntent:
        if not self._open:
            raise RuntimeError("BaselineController is closed")
        until = now_ns + intent_ttl_ns
        cfg = self._config
        if observation.validity_mask.stale or not observation.validity_mask.frame:
            # Stop actuators, but account for the preceding command and elapsed
            # unobserved control interval instead of freezing belief forever.
            self._bearing(observation, cfg)
            diag = ControlDiagnostics(
                attract_turn=0.0,
                avoid_turn=0.0,
                memory_turn=0.0,
                risk=0.0,
                progress=0.0,
                side=self.memory.side,
                side_age=self._side_age,
                turn=0.0,
                forward=0.0,
                stop=True,
                reason="stale",
                target_confidence=0.0,
                situation="unreliable",
            )
            self.last_diag = diag
            return _intent(0.0, 0.0, stop=True, confidence=0.0, until=until)
        nav = _as_nav(observation.navigation)
        mass = observation.visual_features.mass
        progress = _progress(observation, nav, mass - self._prev_mass, cfg)
        self._prev_mass = mass
        left_p, center_p, right_p = _pressures(nav)
        steer_risk, brake_risk = _risk(nav, center_p, cfg)
        visual_front = self._front_blocked(steer_risk, nav, cfg)
        last = observation.previous_action
        if last is not None:
            self._history.append(last)
        if last is not None and last.forward > 0.25 and progress < cfg.stall_progress:
            self._stall += 1
        else:
            self._stall = 0
        if self._stall >= cfg.stall_ticks:
            steer_risk = min(1.0, steer_risk + cfg.k_stall_avoid)
            brake_risk = min(1.0, brake_risk + cfg.k_stall_avoid)
        bearing, conf, live = self._bearing(observation, cfg)
        hard_front = self._hard_front(steer_risk, nav, cfg)
        hold_memory = (
            self.memory.had_target
            and not live
            and not hard_front
            and not self.memory.probe_done
        )
        if conf < cfg.search_conf and not hold_memory:
            self._commit_side_bias(left_p, right_p, visual_front, cfg)
        elif live:
            first_acquire = not self.memory.had_target
            wrapped = self.memory.edge_seen
            self.memory.side_lock = 0
            self.memory.peel_age = 0
            self.memory.had_target = True
            self.memory.slide = False
            self.memory.slide_age = 0
            self.memory.slide_hold = 0
            self.memory.aligning = False
            self.memory.align_age = 0
            self.memory.edge_seen = False
            self.memory.hook_age = 0
            self.memory.slide_clear_seen = False
            if first_acquire and abs(bearing) > 0.05:
                self.memory.side = 1.0 if bearing > 0.0 else -1.0
                self._side_age = 0
            if first_acquire and self.memory.probe_done and not self.memory.shallow:
                if wrapped:
                    self.memory.wrap_sprint = True
                    self.memory.clear_left = cfg.wrap_clear_ticks
                else:
                    self.memory.clear_left = cfg.hook_clear_ticks
            self._update_side(left_p, right_p, steer_risk, cfg)
        side = self.memory.side
        situation = classify_situation(
            observation,
            last,
            nav,
            self.memory.progress_conf,
            mass=mass,
            bearing_norm=bearing,
            conf=conf,
            cfg=cfg,
        )
        current_scene = scene_vector(nav, mass, bearing)
        repeat = scene_similarity(self.memory.scene, current_scene)
        self.memory.scene_repeat_score = repeat
        if current_scene:
            self.memory.scene = current_scene
        self.memory.situation = situation
        self._update_course_lock(bearing, conf, cfg, live=live, hard_front=hard_front)
        update_evidence(
            self.memory,
            last=last,
            progress=progress,
            situation=self.memory.situation,
            repeat=repeat,
            duplicate=bool(nav.duplicate_frame) if nav is not None else False,
            structure=scene_structure(nav),
            cfg=cfg,
            transit=self._course_locked or hold_memory or self.memory.side_lock > 0 or self.memory.peel_age > 0,
        )
        if not hold_memory:
            self._drive_recovery(cfg)
        attract = cfg.k_attract * bearing * conf if live else 0.0
        avoid = cfg.k_avoid * side * steer_risk
        memory_turn = cfg.k_memory * self.memory.side * steer_risk
        align = max(0.0, 1.0 - cfg.bearing_align * abs(bearing)) if live and conf >= cfg.search_conf else 0.0
        if live and conf >= cfg.search_conf:
            avoid *= 1.0 - cfg.aligned_avoid * max(align, 0.35) * min(1.0, max(conf, 0.25))
        raw_turn = attract + avoid + memory_turn
        raw_turn = _persist_turn(raw_turn, last, cfg)
        turn = float(max(-1.0, min(1.0, raw_turn)))
        if hold_memory:
            turn, forward = 0.0, cfg.course_lock_forward
            reason = "seek"
        elif live and conf >= cfg.search_conf:
            speed_scale = min(1.0, conf / max(cfg.target_min_conf, 1e-6))
            forward = cfg.cruise * (1.0 - cfg.k_brake * brake_risk) * max(align, 0.25) * speed_scale
            if self.memory.probe_done and not self.memory.shallow:
                forward = max(forward, cfg.bypass_seek_forward)
            if self.memory.wrap_sprint and abs(bearing) <= cfg.wrap_sprint_bearing:
                forward = max(forward, cfg.wrap_sprint_forward)
            reason: Reason = "avoid" if steer_risk >= cfg.risk_choose else "seek"
        else:
            turn, forward = self._blind_command(visual_front, hard_front, brake_risk, nav, cfg)
            reason = "search"
        if steer_risk >= cfg.risk_choose and abs(self.memory.side) > 0.1:
            reason = "hold" if self._side_age < cfg.side_hold_ticks else reason
        if self.memory.recovering:
            self._course_lock_age = 0
            self._course_locked = False
            turn, forward = recovery_command(self.memory, cfg)
            turn = float(max(-1.0, min(1.0, turn)))
            reason = "recover"
        elif self.memory.clear_left > 0:
            self.memory.clear_left -= 1
            turn = 0.0
            forward = max(forward, cfg.hook_clear_forward)
            reason = "seek"
        elif self._course_locked:
            turn, forward, reason = self._hold_course(bearing, turn, forward, cfg, live=live)
        forward = float(max(0.0, min(1.0, forward)))
        self.last_diag = ControlDiagnostics(
            attract_turn=float(attract),
            avoid_turn=float(avoid),
            memory_turn=float(memory_turn),
            risk=float(brake_risk),
            progress=float(progress),
            side=float(self.memory.side),
            side_age=int(self._side_age),
            turn=turn,
            forward=forward,
            stop=False,
            reason=reason,
            target_confidence=float(conf),
            situation=self.memory.situation,
            progress_conf=self.memory.progress_conf,
            no_progress_evidence=self.memory.no_progress_evidence,
            recovering=self.memory.recovering,
            recover_age=self.memory.recover_age,
            scene_repeat_score=self.memory.scene_repeat_score,
        )
        return _intent(turn, forward, stop=False, confidence=max(conf, 0.15), until=until)

    def close(self) -> None:
        self._open = False
        self.reset_state()

    def _update_side(self, left_p: float, right_p: float, risk: float, cfg: BaselineConfig) -> float:
        self._side_age += 1
        if self.memory.recovering:
            return self.memory.side
        if risk >= cfg.risk_choose and self._side_age >= cfg.side_hold_ticks:
            delta = right_p - left_p
            if abs(delta) > 0.01:
                self.memory.side = 1.0 if delta < 0.0 else -1.0
            elif self.memory.side == 0.0:
                self.memory.side = 1.0
            self._side_age = 0
        return self.memory.side

    def _commit_side_bias(
        self,
        left_p: float,
        right_p: float,
        blocked: bool,
        cfg: BaselineConfig,
    ) -> None:
        """Lock skirt side while the target is unseen. No scene names."""
        if self.memory.recovering:
            return
        if self.memory.side == 0.0:
            delta = right_p - left_p
            self.memory.side = 1.0 if delta < 0.0 else -1.0
            if abs(delta) <= 0.01:
                self.memory.side = 1.0
            self.memory.side_lock = max(cfg.side_bias_ticks, cfg.peel_ticks)
            self.memory.peel_age = 0
        elif self.memory.side_lock > 0:
            self.memory.side_lock -= 1
        self.memory.peel_age += 1
        if blocked:
            self.memory.front_streak += 1
        else:
            self.memory.front_streak = 0

    def _front_blocked(self, steer_risk: float, nav: NavigationChannels | None, cfg: BaselineConfig) -> bool:
        """Occupied frontal sector. Unknown/missing flow is not a wall."""
        expansion = nav.expansion if nav is not None else 0.0
        return steer_risk >= cfg.front_block_steer or expansion >= cfg.front_block_expansion

    def _hard_front(self, steer_risk: float, nav: NavigationChannels | None, cfg: BaselineConfig) -> bool:
        """Contact-like looming. Stall-boosted steer is not a wall."""
        del steer_risk
        expansion = nav.expansion if nav is not None else 0.0
        return expansion >= cfg.hold_break_expansion

    def _frontal_barrier(self, steer_risk: float, nav: NavigationChannels | None, cfg: BaselineConfig) -> bool:
        return self._front_blocked(steer_risk, nav, cfg)

    def _blind_command(
        self,
        blocked: bool,
        hard_front: bool,
        brake_risk: float,
        nav: NavigationChannels | None,
        cfg: BaselineConfig,
    ) -> tuple[float, float]:
        sign = self.memory.side if self.memory.side != 0.0 else 1.0
        if self.memory.had_target and not hard_front and not self.memory.probe_done:
            return 0.0, cfg.course_lock_forward
        if self.memory.had_target:
            if self.memory.probe_done and not self.memory.shallow:
                guide = self.memory.last_bearing
                hook_sign = 1.0 if guide > 0.0 else -1.0
                if abs(guide) <= 0.05:
                    hook_sign = sign
                turn, forward = hook_sign * cfg.trap_peel_turn, cfg.search_peel_forward
            else:
                turn, forward = sign * cfg.skirt_turn, cfg.peel_forward
        elif not self.memory.probe_done:
            turn, forward = self._probe_command(blocked, cfg)
        elif self.memory.shallow:
            turn, forward = sign * cfg.trap_peel_turn, cfg.search_peel_forward
        elif self.memory.peel_age <= cfg.bypass_peel_ticks:
            turn, forward = sign * cfg.skirt_turn, cfg.search_peel_forward
        else:
            turn, forward = self._slide_or_hook(blocked, nav, sign, cfg)
        if self.memory.slide:
            forward = max(cfg.skirt_forward, 0.50)
        else:
            forward = max(forward, 0.0) * (1.0 - 0.20 * brake_risk)
        return float(max(-1.0, min(1.0, turn))), float(max(0.0, min(1.0, forward)))

    def _probe_command(self, blocked: bool, cfg: BaselineConfig) -> tuple[float, float]:
        """Count free forward ticks, then latch shallow trap vs walked-up barrier."""
        mem = self.memory
        warmed = mem.peel_age >= cfg.front_warmup_ticks
        if warmed and blocked:
            mem.probe_done = True
            mem.shallow = mem.probe_distance_ticks < cfg.probe_gate_ticks
            mem.peel_age = 0
            mem.slide = False
            mem.slide_age = 0
            mem.slide_hold = 0
            mem.aligning = False
            mem.align_age = 0
            mem.edge_seen = False
            mem.hook_age = 0
            mem.wrap_sprint = False
            sign = mem.side if mem.side != 0.0 else 1.0
            peel_turn = cfg.trap_peel_turn if mem.shallow else cfg.skirt_turn
            return sign * peel_turn, cfg.search_peel_forward
        if mem.probe_distance_ticks >= cfg.probe_give_up_ticks:
            mem.probe_done = True
            mem.shallow = False
            mem.peel_age = 0
            mem.slide = False
            mem.slide_age = 0
            mem.slide_hold = 0
            mem.aligning = False
            mem.align_age = 0
            mem.edge_seen = False
            mem.hook_age = 0
            mem.wrap_sprint = False
            sign = mem.side if mem.side != 0.0 else 1.0
            return sign * cfg.skirt_turn, cfg.search_peel_forward
        if not blocked:
            mem.probe_distance_ticks += 1
        return 0.0, cfg.probe_forward

    def _slide_or_hook(
        self,
        blocked: bool,
        nav: NavigationChannels | None,
        sign: float,
        cfg: BaselineConfig,
    ) -> tuple[float, float]:
        """Slide, then hook; long edge does align, reslide, and a capped wrap."""
        del nav
        mem = self.memory
        if mem.aligning:
            mem.align_age += 1
            finished = mem.align_age >= cfg.align_ticks
            if finished:
                mem.aligning = False
                mem.slide_hold = cfg.edge_reslide_ticks
                mem.hook_age = 0
                mem.slide = True
                mem.slide_age += 1
                return 0.0, cfg.skirt_forward
            mem.slide = False
            return sign * cfg.trap_peel_turn, cfg.search_peel_forward
        must_slide = mem.slide_age < cfg.min_slide_ticks or mem.slide_hold > 0
        timed_out = mem.slide_age >= cfg.max_slide_ticks
        if must_slide and not timed_out:
            mem.slide_age += 1
            if mem.slide_hold > 0:
                mem.slide_hold -= 1
            mem.hook_age = 0
            mem.slide = True
            return 0.0, cfg.skirt_forward
        mem.slide = False
        mem.slide_hold = 0
        mem.hook_age += 1
        if blocked and mem.hook_age >= cfg.hook_edge_ticks and not mem.edge_seen:
            mem.edge_seen = True
            mem.aligning = True
            mem.align_age = 0
            return sign * cfg.trap_peel_turn, cfg.search_peel_forward
        if mem.edge_seen:
            mem.slide = False
            if mem.hook_age <= cfg.wrap_ticks:
                return -sign * cfg.wrap_turn, cfg.wrap_forward
            exit_end = cfg.wrap_ticks + cfg.wrap_exit_ticks
            seek_end = exit_end + cfg.wrap_seek_ticks
            if mem.hook_age <= exit_end:
                return 0.0, cfg.wrap_exit_forward
            if mem.hook_age <= seek_end:
                return -sign * cfg.wrap_turn, cfg.wrap_exit_forward
            return 0.0, cfg.wrap_exit_forward
        return -sign * cfg.skirt_turn, cfg.hook_forward

    def _update_course_lock(
        self,
        bearing: float,
        conf: float,
        cfg: BaselineConfig,
        *,
        live: bool,
        hard_front: bool,
    ) -> None:
        if hard_front and not live:
            self._course_lock_age = 0
            self._course_locked = False
            return
        if not live:
            return
        aligned = conf >= cfg.search_conf and abs(bearing) <= cfg.course_lock_bearing
        if conf < cfg.search_conf:
            self._course_lock_age = 0
            self._course_locked = False
        elif aligned:
            self._course_lock_age += 1
            if self._course_lock_age >= cfg.course_lock_ticks:
                self._course_locked = True
        elif not self._course_locked:
            self._course_lock_age = 0

    def _hold_course(
        self,
        bearing: float,
        turn: float,
        forward: float,
        cfg: BaselineConfig,
        *,
        live: bool,
    ) -> tuple[float, float, Reason]:
        floor = cfg.wrap_sprint_forward if self.memory.wrap_sprint else cfg.course_lock_forward
        forward = max(forward, floor)
        if not live:
            turn = turn * cfg.course_lock_turn
            return turn, forward, "seek"
        if abs(bearing) <= cfg.course_lock_bearing:
            return 0.0, forward, "seek"
        track = cfg.k_attract * bearing * self.memory.last_bearing_conf
        turn = max(-cfg.course_lock_track, min(cfg.course_lock_track, track))
        return turn, forward, "seek"

    def _bearing(self, observation: Observation, cfg: BaselineConfig) -> tuple[float, float, bool]:
        conf = float(observation.target_confidence)
        raw = observation.target_bearing
        valid = observation.validity_mask.frame and not observation.validity_mask.stale and observation.validity_mask.target
        if valid and raw is not None:
            norm = float(max(-1.0, min(1.0, raw / (0.5 * cfg.fov_rad))))
            feats = observation.visual_features
            compact = feats.center >= 2.0 * max(feats.left, feats.right)
            centered = abs(norm) <= cfg.goal_bearing
            tracked = self.memory.last_bearing_conf >= cfg.track_hold_conf
            acquire = conf >= cfg.target_min_conf
            persist = conf >= cfg.track_hold_conf and (tracked or (centered and compact))
            if acquire or persist:
                self.memory.last_bearing = norm
                self.memory.last_bearing_conf = conf
                self._hold_age = 0
                return norm, conf, True
        if observation.validity_mask.stale or not observation.validity_mask.frame:
            self._hold_age += 1
            self.memory.last_bearing_conf *= cfg.unobs_decay
            if self.memory.last_bearing_conf >= cfg.search_conf:
                return self.memory.last_bearing, self.memory.last_bearing_conf, False
            return 0.0, 0.0, False
        self._hold_age += 1
        self.memory.last_bearing_conf *= cfg.unobs_decay
        if self.memory.last_bearing_conf >= cfg.search_conf:
            return self.memory.last_bearing, self.memory.last_bearing_conf, False
        return 0.0, 0.0, False

    def _drive_recovery(self, cfg: BaselineConfig) -> None:
        mem = self.memory
        if not cfg.recovery:
            return
        if mem.cooldown > 0:
            mem.cooldown -= 1
            if mem.cooldown == 0:
                mem.consecutive_failures = 0
            return
        if mem.situation == "goal_like" and mem.recovering:
            finish_recovery(mem, failed=False)
            return
        if mem.recovering:
            mem.recover_age += 1
            if mem.progress_conf >= cfg.stall_progress + 0.05 and mem.recover_age >= 3:
                finish_recovery(mem, failed=False)
                return
            if mem.recover_age >= cfg.recovery_hold_ticks:
                failed = mem.progress_conf < cfg.stall_progress
                failed_n = mem.consecutive_failures + int(failed)
                if failed and failed_n >= cfg.recover_max_retries:
                    finish_recovery(mem, failed=True, cooldown=cfg.recover_cooldown_ticks)
                    return
                finish_recovery(mem, failed=failed)
                if failed:
                    start_recovery(mem, cfg)
            return
        failed_n = mem.consecutive_failures
        if self._course_locked:
            return
        if mem.side_lock > 0:
            return
        if mem.clear_left > 0:
            return
        if mem.situation == "blocked" and failed_n < cfg.recover_max_retries:
            start_recovery(mem, cfg)


def _intent(turn: float, forward: float, *, stop: bool, confidence: float, until: int) -> MotorIntent:
    return MotorIntent(
        turn=turn,
        forward=0.0 if stop else forward,
        strafe=None,
        stop="fire" if stop else "idle",
        select_target="idle",
        attack="idle",
        confidence=confidence,
        valid_until_ns=until,
    ).clipped()


def _as_nav(payload: object | None) -> NavigationChannels | None:
    return payload if isinstance(payload, NavigationChannels) else None


def _progress(observation: Observation, nav: NavigationChannels | None, d_mass: float, cfg: BaselineConfig) -> float:
    expansion = nav.expansion if nav is not None else 0.0
    body = nav.hypothesis.body_forward_like if nav is not None else 0.0
    value = cfg.w_expansion * max(-1.0, min(1.0, expansion))
    value += cfg.w_mass * max(-1.0, min(1.0, d_mass * 8.0))
    value += cfg.w_body * max(0.0, min(1.0, body))
    return float(value)


def _pressures(nav: NavigationChannels | None) -> tuple[float, float, float]:
    if nav is None:
        return 0.0, 0.0, 0.0
    scale = nav.near
    sx, sy = nav.sectors_x, nav.sectors_y
    left = _pressure(scale, sx, sy, (0, 1) if sx >= 3 else (0,))
    right = _pressure(scale, sx, sy, (sx - 2, sx - 1) if sx >= 3 else (sx - 1,))
    center = _pressure(scale, sx, sy, (sx // 2,))
    return left, center, right


def _pressure(scale: ScaleChannels, sx: int, sy: int, cols: tuple[int, ...]) -> float:
    contrast = _col_mean(scale.contrast, sx, sy, cols)
    d_pos = _col_mean(scale.d_pos, sx, sy, cols)
    bright = _col_mean(scale.brightness, sx, sy, cols)
    return float(0.55 * contrast + 0.35 * d_pos + 0.10 * bright)


def _col_mean(values: tuple[float, ...], sx: int, sy: int, cols: tuple[int, ...]) -> float:
    if not values or sx < 1:
        return 0.0
    acc: list[float] = []
    for iy in range(max(sy, 1)):
        for ix in cols:
            idx = iy * sx + ix
            if 0 <= idx < len(values):
                acc.append(values[idx])
    return float(sum(acc) / len(acc)) if acc else 0.0


def _risk(nav: NavigationChannels | None, center_p: float, cfg: BaselineConfig) -> tuple[float, float]:
    """Steer risk is directional. Missing flow only brakes; it is not a wall."""
    if nav is None:
        steer = min(1.0, cfg.k_center * center_p)
        return steer, steer
    unknown = 0.0
    if nav.flow_absent_is_not_clear:
        unknown = cfg.k_unknown * max(nav.near.weak_texture_frac, 1.0 - nav.near.valid_flow_frac)
    expansion = cfg.k_expansion * max(0.0, nav.expansion)
    residual = cfg.k_residual * max(0.0, nav.hypothesis.residual_object_like / 4.0)
    steer = float(max(0.0, min(1.0, expansion + cfg.k_center * center_p + residual)))
    brake = float(max(0.0, min(1.0, steer + unknown)))
    return steer, brake


def _persist_turn(turn: float, last: PreviousAction | None, cfg: BaselineConfig) -> float:
    if last is None or abs(last.turn) < 0.25:
        return turn
    if turn * last.turn >= 0.0:
        return turn
    return (1.0 - cfg.k_turn_persist) * turn + cfg.k_turn_persist * last.turn
