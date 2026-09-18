"""Stage timings for the synthetic loop. Does not change controllers."""

from __future__ import annotations

import json
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.contracts import Observation, PreviousAction
from l2_brain.control.bench import build_controller
from l2_brain.control.tactical import TacticalCombatController
from l2_brain.experiment.clocks import mono_ns
from l2_brain.factory import build_encoder
from l2_brain.io import DryRunInputBackend, IntentDecoder
from l2_brain.metrics import percentile
from l2_brain.sim.config import catalog
from l2_brain.sim.environment import SimulationEnvironment
from l2_brain.telemetry import RangeCue, TelemetryHub

PROFILE_CONTROLLERS = ("baseline_v1", "gru_v1", "snn_v1")


@dataclass(frozen=True, slots=True)
class StageStats:
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    p50_us: float
    p95_us: float
    n: int

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def _stats(samples_ms: list[float]) -> StageStats:
    arr = np.asarray(samples_ms, dtype=np.float64)
    p50 = float(percentile(samples_ms, 0.50))
    return StageStats(
        p50_ms=p50,
        p95_ms=float(percentile(samples_ms, 0.95)),
        p99_ms=float(percentile(samples_ms, 0.99)),
        max_ms=float(arr.max()) if arr.size else 0.0,
        p50_us=p50 * 1000.0,
        p95_us=float(percentile(samples_ms, 0.95)) * 1000.0,
        n=len(samples_ms),
    )


def _elapsed_ms(start_ns: int) -> float:
    return (mono_ns() - start_ns) / 1_000_000.0


def host_info() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "machine": platform.machine(),
        "mac_ver": platform.mac_ver()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "accel": "numpy_cpu",
    }


def profile_controller(
    name: str,
    *,
    ticks: int = 100,
    warmup: int = 10,
    seed: int = 0,
) -> dict[str, Any]:
    spec = next(
        item
        for item in catalog(seed, suite="frozen")
        if item.scenario == "open_goal" and item.split == "training" and item.variant == 0
    )
    env = SimulationEnvironment(spec)
    enc = build_encoder("navigation_v1")
    ctl = build_controller(name, seed=seed)
    hub = TelemetryHub()
    tactical = TacticalCombatController(hub)
    decoder = IntentDecoder()
    backend = DryRunInputBackend()
    env.initialize()
    enc.initialize()
    ctl.initialize()
    tactical.initialize()
    view = env.reset_episode(spec)
    prev: Observation | None = None
    encode_ms: list[float] = []
    infer_ms: list[float] = []
    tactical_ms: list[float] = []
    decode_ms: list[float] = []
    tick_ms: list[float] = []
    measured = 0
    seen = 0
    try:
        while measured < ticks:
            now = 1_000_000_000 + seen * int(1_000_000_000 / spec.config.tick_hz)
            tick_t0 = mono_ns()
            t0 = mono_ns()
            obs = enc.encode(view.frame, (), prev, now, bool(view.dropped))
            t_encode = _elapsed_ms(t0)
            t0 = mono_ns()
            intent = ctl.step(obs, now, 100_000_000)
            t_infer = _elapsed_ms(t0)
            t0 = mono_ns()
            hub.publish(
                RangeCue(
                    timestamp_ns=now,
                    source="mock",
                    confidence=1.0,
                    distance_m=3.0,
                    in_range=False,
                )
            )
            tactical._advance(obs, now)
            t_tactical = _elapsed_ms(t0)
            t0 = mono_ns()
            for action in decoder.decode(intent):
                backend.send_action(action)
            t_decode = _elapsed_ms(t0)
            view, _gt = env.step(intent)
            total = _elapsed_ms(tick_t0)
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
                previous_action=PreviousAction(intent.turn, intent.forward, intent.pulses),
                navigation=obs.navigation,
            )
            seen += 1
            if env.reached_goal() or seen % spec.config.max_steps == 0:
                view = env.reset_episode(spec)
                ctl.reset_state()
                enc.reset_episode(seed)
                prev = None
            if seen <= warmup:
                continue
            encode_ms.append(t_encode)
            infer_ms.append(t_infer)
            tactical_ms.append(t_tactical)
            decode_ms.append(t_decode)
            tick_ms.append(total)
            measured += 1
    finally:
        env.close()
        enc.close()
        ctl.close()
        tactical.close()
    stages = {
        "t_encode": _stats(encode_ms).to_dict(),
        "t_infer": _stats(infer_ms).to_dict(),
        "t_tactical": _stats(tactical_ms).to_dict(),
        "t_decode": _stats(decode_ms).to_dict(),
        "t_tick": _stats(tick_ms).to_dict(),
    }
    return {
        "controller": name,
        "ticks": measured,
        "warmup": warmup,
        "scenario": spec.episode_id,
        "stages": stages,
        "hid_sent": False,
    }


def run_profile(*, ticks: int = 100, warmup: int = 10, seed: int = 0) -> dict[str, Any]:
    rows = [profile_controller(name, ticks=ticks, warmup=warmup, seed=seed) for name in PROFILE_CONTROLLERS]
    return {
        "suite": "circuit-profile-v0",
        "host": host_info(),
        "hypothesis": "At B=1, MPS does not beat CPU for current sizes; SNN infer p95 already < 2 ms. H6 stays rejected unless both fail.",
        "reject_cpu_if": "Synced MPS p50 < CPU p50 at N=64 B=1 AND controller infer p95 >= 2 ms.",
        "optimized": False,
        "transfer_claim": False,
        "rows": rows,
    }


def write_profile(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
