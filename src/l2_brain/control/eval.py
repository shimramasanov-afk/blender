from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from l2_brain.contracts import Observation, PreviousAction
from l2_brain.control.ablation import apply_channel_ablation
from l2_brain.control.baseline import BaselineController, ControlDiagnostics
from l2_brain.control.config import BaselineConfig
from l2_brain.control.events import rate_or_na, score_events
from l2_brain.experiment.clocks import mono_ns
from l2_brain.experiment.identity import code_identity
from l2_brain.sim.config import EpisodeSpec, SimConfig, catalog
from l2_brain.sim.environment import SimulationEnvironment
from l2_brain.sim.observability import goal_observable
from l2_brain.sim.views import EpisodeResult, GroundTruth
from l2_brain.sim.world import wrap
from l2_brain.factory import build_encoder

Outcome = Literal["success", "oscillate", "stuck", "timeout"]
Cause = Literal["none", "vision", "control", "mixed", "stale"]

TRANSFER = "synthetic stand baseline; not MMORPG transfer; not a claim that SNN or memory is better"


@dataclass(frozen=True, slots=True)
class BaselineEpisode:
    episode_id: str
    scenario: str
    split: str
    variant: int
    seed: int
    success: bool
    timeout: bool
    outcome: Outcome
    cause: Cause
    collisions: int
    no_progress: bool
    direction_changes: int
    path_length: float
    net_displacement: float
    ticks: int
    vision_miss_rate: float | None
    bearing_err_rad_p50: float | None
    mean_risk: float
    mean_progress: float
    mean_target_conf: float
    infer_ms_p50: float
    encode_ms_p50: float
    stale_ticks: int
    gt_stuck_windows: int
    detections: int
    true_positives: int
    false_positives: int
    recoveries: int
    recovery_successes: int
    recovery_time_p50: float | None
    retraps: int
    events: dict[str, Any]
    transfer_claim: bool
    limitation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_episode(
    spec: EpisodeSpec,
    *,
    config: BaselineConfig | None = None,
    encoder: object | None = None,
    controller: object | None = None,
) -> tuple[BaselineEpisode, EpisodeResult]:
    env = SimulationEnvironment(spec)
    ctl = controller if controller is not None else BaselineController(config)
    enc = encoder or build_encoder("navigation_v1")
    own_encoder = encoder is None
    env.initialize()
    ctl.initialize()
    if own_encoder:
        enc.initialize()
    else:
        enc.reset_episode(spec.seed)
    ctl.reset_state()
    view = env.reset_episode(spec)
    frame_gt = env._truth(contact=False, dropped=view.dropped, delayed=False)
    prev: Observation | None = None
    truths: list[GroundTruth] = [frame_gt]
    diags: list[ControlDiagnostics] = []
    encodes: list[float] = []
    infers: list[float] = []
    stale_ticks = 0
    confs: list[float] = []
    misses = 0
    in_fov = 0
    bearing_errs: list[float] = []
    traces: list[dict[str, Any]] = []
    success = env.reached_goal()
    timeout = False
    try:
        for step_i in range(spec.config.max_steps):
            if success:
                break
            stale = bool(view.dropped)
            now = 1_000_000_000 + step_i * int(1_000_000_000 / spec.config.tick_hz)
            t0 = mono_ns()
            obs = enc.encode(view.frame, (), prev, now, stale)
            encodes.append((mono_ns() - t0) / 1_000_000.0)
            _vision_sample(obs, frame_gt, spec.config.fov_h, confs, bearing_errs)
            cfg = config or BaselineConfig()
            misses, in_fov = _count_vision(obs, frame_gt, spec.config.fov_h, misses, in_fov,
                                           min_conf=cfg.target_min_conf)
            policy_obs = apply_channel_ablation(obs, cfg.channels)
            t1 = mono_ns()
            intent = ctl.step(policy_obs, now, 100_000_000)
            infers.append((mono_ns() - t1) / 1_000_000.0)
            diag = getattr(ctl, "last_diag", None)
            if diag is not None:
                diags.append(diag)
                if getattr(diag, "stop", False):
                    stale_ticks += 1
            view, gt = env.step(intent)
            truths.append(gt)
            traces.append(
                {
                    "dist": gt.distance_to_goal,
                    "x": gt.agent_xy[0],
                    "y": gt.agent_xy[1],
                    "contact": gt.obstacle_contact,
                    "cmd_forward": intent.forward,
                    "applied_forward": (0.0 if env.last_applied_intent.stop == "fire"
                                        else env.last_applied_intent.forward),
                    "previous_x": frame_gt.agent_xy[0],
                    "previous_y": frame_gt.agent_xy[1],
                    "recovering": bool(getattr(diag, "recovering", False)) if diag else False,
                    "situation": getattr(diag, "situation", "move") if diag else "move",
                    "evidence": getattr(diag, "no_progress_evidence", 0.0) if diag else 0.0,
                    "reason": getattr(diag, "reason", "seek") if diag else "seek",
                    "goal_visible": frame_gt.goal_visible,
                    "in_fov": goal_observable(frame_gt, spec.config.fov_h),
                    "dropped": frame_gt.dropped_frame,
                    "stale": stale,
                }
            )
            frame_gt = gt
            prev = Observation(
                timestamp_ns=obs.timestamp_ns,
                frame_id=obs.frame_id,
                visual_features=obs.visual_features,
                target_bearing=obs.target_bearing,
                target_confidence=obs.target_confidence,
                motion_estimate=obs.motion_estimate,
                motion_confidence=obs.motion_confidence,
                telemetry=obs.telemetry,
                validity_mask=obs.validity_mask,
                previous_action=PreviousAction(
                    turn=intent.turn,
                    forward=intent.forward,
                    pulses=intent.pulses,
                ),
                navigation=obs.navigation,
            )
            success = env.reached_goal()
        else:
            timeout = not success
        result = env.result(success=success, timeout=timeout)
    finally:
        env.close()
        ctl.close()
        if own_encoder:
            enc.close()
    episode = _summarize(
        spec, result, truths, diags, encodes, infers, stale_ticks, confs, bearing_errs, misses, in_fov, traces
    )
    return episode, result


def run_catalog(
    seed: int,
    *,
    config: BaselineConfig | None = None,
    split: str | None = None,
    scenarios: tuple[str, ...] | None = None,
    max_steps: int | None = None,
    sim: SimConfig | None = None,
    suite: str = "frozen",
    encoder_name: str = "navigation_v1",
    controller: object | None = None,
) -> list[BaselineEpisode]:
    specs = catalog(seed, config=sim, suite=suite)
    if split is not None:
        specs = [item for item in specs if item.split == split]
    if scenarios is not None:
        allowed = set(scenarios)
        specs = [item for item in specs if item.scenario in allowed]
    if max_steps is not None:
        from dataclasses import replace

        specs = [
            EpisodeSpec(
                scenario=item.scenario,
                split=item.split,
                variant=item.variant,
                seed=item.seed,
                config=replace(item.config, max_steps=max_steps),
            )
            for item in specs
        ]
    rows: list[BaselineEpisode] = []
    enc = build_encoder(encoder_name)
    enc.initialize()
    try:
        for spec in specs:
            enc.reset_episode(spec.seed)
            row, _result = run_episode(spec, config=config, encoder=enc, controller=controller)
            rows.append(row)
    finally:
        enc.close()
    return rows


def write_report(path: Path, rows: list[BaselineEpisode], *, extras: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "suite": "nav-sim-v1",
        "controller": extras.get("controller") if extras and extras.get("controller") else "baseline_memory_v1",
        "encoder": (extras or {}).get("encoder_name") or "navigation_v1",
        "learned": False,
        "metrics_version": "repair-20260917",
        "recovery_time_unit": "seconds",
        "visibility_model": "target centre LOS/FOV; not pixel-perfect visibility",
        "transfer_claim": False,
        "limitation": TRANSFER,
        "code": code_identity(),
        "hypothesis": (extras or {}).get("hypothesis")
        or (
            "Short-term memory plus explicit recovery improves dead-end and U-trap "
            "results versus baseline_v1 without a large drop on simple scenes."
        ),
        "reject_if": (extras or {}).get("reject_if")
        or (
            "Trap success falls, or simple-scene success drops by more than 2 episodes "
            "on the same seed catalog."
        ),
        "summary": summarize_rows(rows),
        "episodes": [row.to_dict() for row in rows],
        "extras": extras or {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def summarize_rows(rows: list[BaselineEpisode]) -> dict[str, Any]:
    outcomes = Counter(row.outcome for row in rows)
    causes = Counter(row.cause for row in rows)
    by_scenario: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = by_scenario.setdefault(
            row.scenario,
            {"n": 0, "success": 0, "outcomes": Counter(), "causes": Counter()},
        )
        bucket["n"] += 1
        bucket["success"] += int(row.success)
        bucket["outcomes"][row.outcome] += 1
        bucket["causes"][row.cause] += 1
    by_split: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = by_split.setdefault(row.split, {"n": 0, "success": 0})
        bucket["n"] += 1
        bucket["success"] += int(row.success)
    return {
        "n": len(rows),
        "successes": sum(int(row.success) for row in rows),
        "outcomes": dict(outcomes),
        "causes": dict(causes),
        "by_scenario": {
            name: {
                "n": item["n"],
                "success": item["success"],
                "outcomes": dict(item["outcomes"]),
                "causes": dict(item["causes"]),
            }
            for name, item in by_scenario.items()
        },
        "by_split": by_split,
        "infer_ms_p50": _median([row.infer_ms_p50 for row in rows]) if rows else 0.0,
        "encode_ms_p50": _median([row.encode_ms_p50 for row in rows]) if rows else 0.0,
        "recovery": {
            "gt_stuck_windows": sum(row.gt_stuck_windows for row in rows),
            "detections": sum(row.detections for row in rows),
            "true_positives": sum(row.true_positives for row in rows),
            "false_positives": sum(row.false_positives for row in rows),
            "recall": rate_or_na(sum(row.true_positives for row in rows), sum(row.gt_stuck_windows for row in rows)),
            "precision": rate_or_na(sum(row.true_positives for row in rows), sum(row.detections for row in rows)),
            "recoveries": sum(row.recoveries for row in rows),
            "recovery_successes": sum(row.recovery_successes for row in rows),
            "recovery_success_rate": rate_or_na(
                sum(row.recovery_successes for row in rows), sum(row.recoveries for row in rows)
            ),
            "recovery_time_p50": (
                _median([row.recovery_time_p50 for row in rows if row.recovery_time_p50 is not None])
                if any(row.recovery_time_p50 is not None for row in rows)
                else None
            ),
            "retraps": sum(row.retraps for row in rows),
        },
        "events": _summarize_events(rows),
    }


def _summarize(
    spec: EpisodeSpec,
    result: EpisodeResult,
    truths: list[GroundTruth],
    diags: list[ControlDiagnostics],
    encodes: list[float],
    infers: list[float],
    stale_ticks: int,
    confs: list[float],
    bearing_errs: list[float],
    misses: int,
    in_fov: int,
    traces: list[dict[str, Any]],
) -> BaselineEpisode:
    net = 0.0
    if truths:
        x0, y0 = truths[0].agent_xy
        x1, y1 = truths[-1].agent_xy
        net = math.hypot(x1 - x0, y1 - y0)
    outcome = _outcome(result, net)
    cause = _cause(result, outcome, diags, misses, in_fov, bearing_errs, stale_ticks)
    rec = score_recovery(traces, tick_hz=spec.config.tick_hz)
    events = score_events(traces, success=result.success, timeout=result.timeout, tick_hz=spec.config.tick_hz)
    return BaselineEpisode(
        episode_id=result.episode_id,
        scenario=result.scenario,
        split=result.split,
        variant=result.variant,
        seed=result.seed,
        success=result.success,
        timeout=result.timeout,
        outcome=outcome,
        cause=cause,
        collisions=result.collisions,
        no_progress=result.no_progress,
        direction_changes=result.direction_changes,
        path_length=result.path_length,
        net_displacement=net,
        ticks=result.ticks,
        vision_miss_rate=rate_or_na(misses, in_fov),
        bearing_err_rad_p50=_median(bearing_errs) if bearing_errs else None,
        mean_risk=float(np.mean([d.risk for d in diags])) if diags else 0.0,
        mean_progress=float(np.mean([d.progress for d in diags])) if diags else 0.0,
        mean_target_conf=float(np.mean(confs)) if confs else 0.0,
        infer_ms_p50=_median(infers),
        encode_ms_p50=_median(encodes),
        stale_ticks=stale_ticks,
        gt_stuck_windows=rec["gt_stuck_windows"],
        detections=rec["detections"],
        true_positives=rec["true_positives"],
        false_positives=rec["false_positives"],
        recoveries=rec["recoveries"],
        recovery_successes=rec["recovery_successes"],
        recovery_time_p50=rec["recovery_time_p50"],
        retraps=rec["retraps"],
        events=events,
        transfer_claim=False,
        limitation=TRANSFER,
    )


def score_recovery(traces: list[dict[str, Any]], *, tick_hz: int = 20) -> dict[str, Any]:
    """GT physical blockage = commanded motion + almost no pose change, long enough. Not flow."""
    from l2_brain.control.events import PHYSICAL_BLOCK_S, ticks_for

    windows = _gt_stuck_windows(traces, min_len=ticks_for(PHYSICAL_BLOCK_S, tick_hz))
    detect_starts = _rising(traces, "recovering") + [
        i for i, row in enumerate(traces) if row.get("situation") == "blocked" and (i == 0 or traces[i - 1].get("situation") != "blocked")
    ]
    detect_starts = sorted(set(detect_starts))
    # One detection can match one GT event only. A late detection within a long
    # blockage is valid; unmatched detections are false positives even at rest.
    tolerance = ticks_for(PHYSICAL_BLOCK_S, tick_hz)
    used: set[int] = set()
    true_pos = 0
    for tick in detect_starts:
        candidates = [(i, end) for i, (start, end) in enumerate(windows)
                      if i not in used and start <= tick <= end + tolerance]
        if candidates:
            index, _ = min(candidates, key=lambda pair: pair[1])
            used.add(index)
            true_pos += 1
    false_pos = len(detect_starts) - true_pos
    recover_starts = _rising(traces, "recovering")
    successes = 0
    times: list[float] = []
    for start in recover_starts:
        dt = _recovery_delay(traces, start, horizon=ticks_for(2.0, tick_hz))
        if dt is not None:
            successes += 1
            times.append(float(dt) / tick_hz)
    retraps = 0
    if successes and len(windows) >= 2:
        first_success = None
        for start in recover_starts:
            if _recovery_delay(traces, start, horizon=ticks_for(2.0, tick_hz)) is not None:
                first_success = start
                break
        if first_success is not None:
            retraps = sum(1 for start, _end in windows if start > first_success + tolerance)
    return {
        "gt_stuck_windows": len(windows),
        "detections": len(detect_starts),
        "true_positives": true_pos,
        "false_positives": false_pos,
        "recoveries": len(recover_starts),
        "recovery_successes": successes,
        "recovery_time_p50": _median(times) if times else None,
        "recovery_time_unit": "seconds",
        "retraps": retraps,
    }


def compare_rows(base: list[dict[str, Any]], next_rows: list[BaselineEpisode]) -> dict[str, Any]:
    traps = ("u_trap", "dead_end")
    simple = ("open_goal", "camera_spin", "moving_target")

    def group(rows: list[Any], names: tuple[str, ...]) -> dict[str, Any]:
        picked = [row for row in rows if _scenario(row) in names]
        succ = sum(int(_success(row)) for row in picked)
        ticks = [_ticks(row) for row in picked if _success(row)]
        return {"n": len(picked), "success": succ, "ticks_p50": _median(ticks) if ticks else None}

    return {
        "traps": {"base": group(base, traps), "memory": group(next_rows, traps)},
        "simple": {"base": group(base, simple), "memory": group(next_rows, simple)},
    }


def _scenario(row: Any) -> str:
    return row.scenario if isinstance(row, BaselineEpisode) else str(row.get("scenario", ""))


def _success(row: Any) -> bool:
    return bool(row.success if isinstance(row, BaselineEpisode) else row.get("success"))


def _ticks(row: Any) -> float:
    return float(row.ticks if isinstance(row, BaselineEpisode) else row.get("ticks", 0))


def _gt_stuck_windows(traces: list[dict[str, Any]], *, min_len: int = 8) -> list[tuple[int, int]]:
    from l2_brain.control.events import _gt_block_flags, _windows

    return _windows(_gt_block_flags(traces), min_len)


def _rising(traces: list[dict[str, Any]], key: str) -> list[int]:
    out: list[int] = []
    prev = False
    for i, row in enumerate(traces):
        cur = bool(row.get(key))
        if cur and not prev:
            out.append(i)
        prev = cur
    return out


def _progressing(traces: list[dict[str, Any]], tick: int) -> bool:
    lo = max(0, tick - 6)
    hi = min(len(traces) - 1, tick + 2)
    if hi <= lo:
        return False
    return traces[lo]["dist"] - traces[hi]["dist"] > 0.18


def _recovery_delay(traces: list[dict[str, Any]], start: int, *, horizon: int = 40) -> int | None:
    if start >= len(traces):
        return None
    x0, y0, d0 = traces[start]["x"], traces[start]["y"], traces[start]["dist"]
    for i in range(start + 1, min(len(traces), start + horizon)):
        moved = math.hypot(traces[i]["x"] - x0, traces[i]["y"] - y0)
        if d0 - traces[i]["dist"] >= 0.35 or moved >= 0.45:
            return i - start
    return None


def _summarize_events(rows: list[BaselineEpisode]) -> dict[str, Any]:
    if not rows:
        return {}
    gt_block = sum(int(row.events.get("gt", {}).get("physical_blockage", False)) for row in rows)
    return {
        "physical_blockage_episodes": gt_block,
        "navigation_stagnation_episodes": sum(
            int(row.events.get("gt", {}).get("navigation_stagnation", False)) for row in rows
        ),
        "target_unobserved_episodes": sum(int(row.events.get("gt", {}).get("target_unobserved", False)) for row in rows),
        "searching_episodes": sum(int(row.events.get("controller", {}).get("searching", False)) for row in rows),
        "observation_invalid_episodes": sum(
            int(row.events.get("gt", {}).get("observation_invalid", False)) for row in rows
        ),
        "episode_timeout_episodes": sum(int(row.events.get("gt", {}).get("episode_timeout", False)) for row in rows),
        "physical_blockage_recall": rate_or_na(sum(row.true_positives for row in rows), sum(row.gt_stuck_windows for row in rows)),
    }


def _outcome(result: EpisodeResult, net: float) -> Outcome:
    if result.success:
        return "success"
    weaving = result.direction_changes >= 8 and result.path_length > 2.4 * max(net, 0.35)
    if weaving:
        return "oscillate"
    if result.no_progress or (result.collisions >= 6 and net < 1.0):
        return "stuck"
    return "timeout"


def _cause(
    result: EpisodeResult,
    outcome: Outcome,
    diags: list[ControlDiagnostics],
    misses: int,
    in_fov: int,
    bearing_errs: list[float],
    stale_ticks: int,
) -> Cause:
    if outcome == "success":
        return "none"
    if stale_ticks >= max(3, result.ticks // 4) and not result.success:
        return "stale"
    if in_fov == 0:
        # No observable target samples: cannot establish a detector failure.
        return "mixed"
    miss_rate = (misses / in_fov) if in_fov else 1.0
    err = _median(bearing_errs) if bearing_errs else None
    vision = miss_rate > 0.40 or (err is not None and err > 0.35)
    mean_conf = float(np.mean([d.target_confidence for d in diags])) if diags else 0.0
    usable = mean_conf >= 0.20 and (err is None or err <= 0.35)
    control = usable and (result.collisions >= 3 or outcome in {"oscillate", "stuck"})
    if vision and control:
        return "mixed"
    if vision:
        return "vision"
    if control:
        return "control"
    if miss_rate > 0.25:
        return "vision"
    return "control"


def _count_vision(
    obs: Observation,
    gt: GroundTruth,
    fov_h: float,
    misses: int,
    in_fov: int,
    *, min_conf: float = 0.12,
) -> tuple[int, int]:
    if not obs.validity_mask.stale and obs.validity_mask.frame and goal_observable(gt, fov_h):
        in_fov += 1
        if not obs.validity_mask.target or obs.target_bearing is None or obs.target_confidence < min_conf:
            misses += 1
    return misses, in_fov


def _vision_sample(
    obs: Observation,
    gt: GroundTruth,
    fov_h: float,
    confs: list[float],
    bearing_errs: list[float],
) -> None:
    confs.append(obs.target_confidence)
    rel = _goal_rel(gt)
    if (not obs.validity_mask.stale and obs.validity_mask.frame and obs.validity_mask.target
            and goal_observable(gt, fov_h) and obs.target_bearing is not None):
        image_bearing = -rel
        bearing_errs.append(abs(obs.target_bearing - image_bearing))


def _goal_rel(gt: GroundTruth) -> float:
    dx = gt.goal_xy[0] - gt.agent_xy[0]
    dy = gt.goal_xy[1] - gt.agent_xy[1]
    return wrap(math.atan2(dy, dx) - gt.camera_yaw)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(np.median(np.asarray(values, dtype=np.float64)))
