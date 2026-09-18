from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Literal

from l2_brain.contracts import Observation, PreviousAction
from l2_brain.control.config import BaselineConfig
from l2_brain.vision.channels import NavigationChannels

Situation = Literal["stand", "camera_turn", "goal_like", "unreliable", "blocked", "move"]


@dataclass(frozen=True, slots=True)
class RecoveryAttempt:
    side: float
    turn_sign: float
    ticks: int
    failed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ShortTermMemory:
    """Compact working memory. No world coordinates, no route graph."""

    last_bearing: float = 0.0
    last_bearing_conf: float = 0.0
    side: float = 0.0
    side_lock: int = 0
    peel_age: int = 0
    had_target: bool = False
    initial_front_blocked: bool | None = None
    slide: bool = False
    slide_clear_seen: bool = False
    approach_ticks: int = 0
    unwind: bool = False
    unwound: bool = False
    search_committed: bool = False
    slide_age: int = 0
    slide_hold: int = 0
    aligning: bool = False
    align_age: int = 0
    edge_seen: bool = False
    hook_age: int = 0
    restoring: bool = False
    front_streak: int = 0
    probe_distance_ticks: int = 0
    probe_done: bool = False
    shallow: bool = False
    clear_left: int = 0
    wrap_sprint: bool = False
    progress_conf: float = 0.0
    no_progress_evidence: float = 0.0
    evidence_age: int = 0
    scene: tuple[float, ...] = ()
    scene_repeat_score: float = 0.0
    situation: Situation = "unreliable"
    recovering: bool = False
    recover_age: int = 0
    recover_sign: float = 0.0
    cooldown: int = 0
    consecutive_failures: int = 0
    attempts: deque[RecoveryAttempt] | None = None

    def __post_init__(self) -> None:
        if self.attempts is None:
            self.attempts = deque(maxlen=8)

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_bearing": self.last_bearing,
            "last_bearing_conf": self.last_bearing_conf,
            "side": self.side,
            "side_lock": self.side_lock,
            "peel_age": self.peel_age,
            "had_target": self.had_target,
            "initial_front_blocked": self.initial_front_blocked,
            "slide": self.slide,
            "slide_clear_seen": self.slide_clear_seen,
            "approach_ticks": self.approach_ticks,
            "unwind": self.unwind,
            "unwound": self.unwound,
            "search_committed": self.search_committed,
            "slide_age": self.slide_age,
            "slide_hold": self.slide_hold,
            "aligning": self.aligning,
            "align_age": self.align_age,
            "edge_seen": self.edge_seen,
            "hook_age": self.hook_age,
            "restoring": self.restoring,
            "front_streak": self.front_streak,
            "probe_distance_ticks": self.probe_distance_ticks,
            "probe_done": self.probe_done,
            "shallow": self.shallow,
            "clear_left": self.clear_left,
            "wrap_sprint": self.wrap_sprint,
            "progress_conf": self.progress_conf,
            "no_progress_evidence": self.no_progress_evidence,
            "evidence_age": self.evidence_age,
            "scene_repeat_score": self.scene_repeat_score,
            "situation": self.situation,
            "recovering": self.recovering,
            "recover_age": self.recover_age,
            "recover_sign": self.recover_sign,
            "cooldown": self.cooldown,
            "consecutive_failures": self.consecutive_failures,
            "attempts": [item.to_dict() for item in (self.attempts or ())],
        }


def classify_situation(
    observation: Observation,
    last: PreviousAction | None,
    nav: NavigationChannels | None,
    progress_conf: float,
    *,
    mass: float,
    bearing_norm: float,
    conf: float,
    cfg: BaselineConfig,
) -> Situation:
    if observation.validity_mask.stale or not observation.validity_mask.frame:
        return "unreliable"
    if nav is not None and (nav.abrupt_cut or nav.lighting_change > 0.20):
        return "unreliable"
    if last is None or (abs(last.turn) < 0.08 and last.forward < 0.08):
        return "stand"
    if mass >= cfg.goal_mass and abs(bearing_norm) <= cfg.goal_bearing and conf >= cfg.target_min_conf:
        return "goal_like"
    camera = False
    if nav is not None and nav.hypothesis.label == "camera_turn":
        camera = True
    if last.forward < 0.15 and abs(last.turn) >= 0.40:
        camera = True
    if camera:
        return "camera_turn"
    return "move"


def scene_vector(nav: NavigationChannels | None, mass: float, bearing: float) -> tuple[float, ...]:
    if nav is None:
        return (round(mass, 3), round(bearing, 2))
    bright = tuple(round(v, 3) for v in nav.far.brightness[:15])
    contrast = tuple(round(v, 3) for v in nav.near.contrast[:15])
    return bright + contrast + (round(mass, 3), round(bearing, 2), round(nav.expansion, 3))


def scene_structure(nav: NavigationChannels | None) -> float:
    """Near-field contrast plus looming. Empty sky is not a trap signature."""
    if nav is None:
        return 0.0
    contrast = nav.near.contrast
    d_pos = nav.near.d_pos
    c_mean = sum(abs(v) for v in contrast) / max(len(contrast), 1)
    d_mean = sum(abs(v) for v in d_pos) / max(len(d_pos), 1)
    return float(c_mean + d_mean)


def scene_similarity(prev: tuple[float, ...], curr: tuple[float, ...]) -> float:
    if not prev or not curr or len(prev) != len(curr):
        return 0.0
    dot = sum(a * b for a, b in zip(prev, curr, strict=True))
    na = sum(a * a for a in prev) ** 0.5
    nb = sum(b * b for b in curr) ** 0.5
    if na < 1e-6 or nb < 1e-6:
        return 0.0
    return float(max(0.0, min(1.0, dot / (na * nb))))


def update_evidence(
    memory: ShortTermMemory,
    *,
    last: PreviousAction | None,
    progress: float,
    situation: Situation,
    repeat: float,
    duplicate: bool,
    structure: float,
    cfg: BaselineConfig,
    transit: bool = False,
) -> None:
    memory.progress_conf = (1.0 - cfg.progress_ema) * memory.progress_conf + cfg.progress_ema * progress
    commanded = last is not None and last.forward >= cfg.cmd_forward_min
    structured = structure >= cfg.structure_min
    repeated = structured and (repeat >= cfg.scene_repeat or duplicate)
    excluded = transit or situation in {"stand", "camera_turn", "goal_like", "unreliable"}
    eligible = commanded and situation == "move" and memory.progress_conf < cfg.stall_progress and repeated and not excluded
    if eligible:
        memory.no_progress_evidence = min(1.0, memory.no_progress_evidence + cfg.evidence_inc)
        memory.evidence_age += 1
    else:
        memory.no_progress_evidence = max(0.0, memory.no_progress_evidence - cfg.evidence_dec)
        if memory.no_progress_evidence < 0.2:
            memory.evidence_age = 0
    blocked = (
        memory.no_progress_evidence >= cfg.evidence_stuck
        and memory.evidence_age >= cfg.evidence_min_ticks
        and situation == "move"
        and structured
    )
    if blocked:
        memory.situation = "blocked"


def choose_recovery_sign(memory: ShortTermMemory) -> float:
    failed = [item.turn_sign for item in (memory.attempts or ()) if item.failed]
    if failed:
        last = failed[-1]
        candidate = -1.0 if last >= 0.0 else 1.0
        if failed[-2:] == [candidate, candidate]:
            return -candidate
        return candidate
    if memory.side != 0.0:
        return -memory.side
    if memory.last_bearing != 0.0:
        return 1.0 if memory.last_bearing < 0.0 else -1.0
    return 1.0


def start_recovery(memory: ShortTermMemory, cfg: BaselineConfig) -> None:
    sign = choose_recovery_sign(memory)
    memory.recovering = True
    memory.recover_age = 0
    memory.recover_sign = sign
    memory.side = sign
    attempts = memory.attempts if memory.attempts is not None else deque(maxlen=cfg.attempt_memory)
    attempts.append(RecoveryAttempt(side=sign, turn_sign=sign, ticks=0, failed=False))
    memory.attempts = attempts


def finish_recovery(memory: ShortTermMemory, *, failed: bool, cooldown: int = 0) -> None:
    attempts = memory.attempts
    if attempts:
        last = attempts[-1]
        attempts[-1] = RecoveryAttempt(
            side=last.side,
            turn_sign=last.turn_sign,
            ticks=memory.recover_age,
            failed=failed,
        )
    memory.recovering = False
    memory.recover_age = 0
    memory.consecutive_failures = memory.consecutive_failures + 1 if failed else 0
    if not failed:
        memory.no_progress_evidence = 0.0
        memory.evidence_age = 0
    if cooldown > 0:
        memory.cooldown = cooldown
        memory.no_progress_evidence = 0.0
        memory.evidence_age = 0


def recovery_command(memory: ShortTermMemory, cfg: BaselineConfig) -> tuple[float, float]:
    """Turn-in-place then crawl. Motor forward is [0, 1]; retreat is a heading change."""
    age = memory.recover_age
    sign = memory.recover_sign if memory.recover_sign != 0.0 else 1.0
    if age < cfg.recovery_backoff_ticks:
        return sign * cfg.recovery_turn, 0.0
    return sign * 0.35 * cfg.recovery_turn, cfg.recovery_crawl
