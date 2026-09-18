"""One-scene MaleCNS topology compare. Not Frozen 60. Not H11."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.control.eval import run_episode
from l2_brain.control.malecns.controller import MaleCNSController
from l2_brain.control.malecns.loader import load_subgraph
from l2_brain.control.snn import LIFConfig, SNNController
from l2_brain.experiment.clocks import mono_ns
from l2_brain.sim.config import catalog

CONTROLLERS = ("snn_v1", "malecns_bio", "malecns_shuffled", "malecns_random")
EPISODE_ID = "open_goal:training:v0:s0"


@dataclass(frozen=True, slots=True)
class CompareRow:
    controller: str
    episode_id: str
    outcome: str
    success: bool
    ticks: int
    collisions: int
    infer_ms_p50: float
    infer_ms_p95: float
    mean_firing_rate_hz: float
    n: int
    e: int
    density: float
    extract_id: str
    biological_claim: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _Meter:
    def __init__(self, inner: object) -> None:
        self.inner = inner
        self.infer_ms: list[float] = []
        self.rates: list[float] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def step(self, observation: object, now_ns: int, intent_ttl_ns: int) -> object:
        t0 = mono_ns()
        intent = self.inner.step(observation, now_ns, intent_ttl_ns)
        self.infer_ms.append((mono_ns() - t0) / 1_000_000.0)
        metrics = getattr(self.inner, "last_metrics", None)
        if metrics is not None:
            self.rates.append(float(metrics.firing_rate_hz))
        return intent


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    return float(np.quantile(np.asarray(values, dtype=np.float64), q))


def open_goal_spec(seed: int = 0):
    return next(
        item
        for item in catalog(seed, suite="frozen")
        if item.scenario == "open_goal" and item.split == "training" and item.variant == 0
    )


def build_controller(name: str, *, seed: int = 0) -> object:
    if name == "snn_v1":
        return SNNController(LIFConfig(seed=seed))
    modes = {
        "malecns_bio": "bio",
        "malecns_shuffled": "shuffled",
        "malecns_random": "random_sparse",
    }
    if name not in modes:
        raise ValueError(f"unknown controller {name}")
    return MaleCNSController(modes[name], seed=seed)  # type: ignore[arg-type]


def run_malecns_compare(*, seed: int = 0, names: tuple[str, ...] = CONTROLLERS) -> list[CompareRow]:
    spec = open_goal_spec(seed)
    if spec.episode_id != EPISODE_ID:
        raise RuntimeError(f"expected {EPISODE_ID}, got {spec.episode_id}")
    rows: list[CompareRow] = []
    for name in names:
        inner = build_controller(name, seed=seed)
        meter = _Meter(inner)
        episode, _result = run_episode(spec, controller=meter)
        if name == "snn_v1":
            n, e, density, extract_id = 64, 0, 0.20, "snn_core_v1"
            claim = False
        else:
            graph = inner.graph
            n, e, density, extract_id = graph.n, graph.e, graph.density, graph.extract_id
            claim = False
        rows.append(
            CompareRow(
                controller=name,
                episode_id=episode.episode_id,
                outcome=episode.outcome,
                success=episode.success,
                ticks=episode.ticks,
                collisions=episode.collisions,
                infer_ms_p50=_percentile(meter.infer_ms, 0.50),
                infer_ms_p95=_percentile(meter.infer_ms, 0.95),
                mean_firing_rate_hz=float(np.mean(meter.rates)) if meter.rates else 0.0,
                n=n,
                e=e,
                density=density,
                extract_id=extract_id,
                biological_claim=claim,
            )
        )
    return rows


def write_comparison(path: Path, rows: list[CompareRow]) -> dict[str, Any]:
    bio = next(row for row in rows if row.controller == "malecns_bio")
    shuffled = next(row for row in rows if row.controller == "malecns_shuffled")
    graph = load_subgraph("bio")
    payload = {
        "suite": "malecns-extract-v0",
        "episode_id": EPISODE_ID,
        "n_runs": 1,
        "hypothesis": (
            "On open_goal:training:v0:s0, native extract topology (bio) finishes in "
            "fewer ticks than a degree-preserving shuffle. Reference is snn_v1. "
            "Not Frozen 60. Not H11."
        ),
        "reject_if": (
            "NaN, missing vis→DN path in bio, Observation leak, or this table is "
            "published as FlyEM download / MaleCNS game policy / catalog ranking."
        ),
        "extract": graph.metadata(),
        "full_connectome_loaded": False,
        "frozen60": False,
        "h11_claim": False,
        "transfer_claim": False,
        "biological_claim": False,
        "bio_ticks_lt_shuffled": bio.ticks < shuffled.ticks,
        "rows": [row.to_dict() for row in rows],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def format_table(rows: list[CompareRow]) -> str:
    header = (
        f"{'controller':20} {'out':8} {'ticks':>5} {'col':>3} "
        f"{'p50ms':>7} {'rate':>7} {'N':>4} {'E':>5}"
    )
    lines = [header]
    for row in rows:
        lines.append(
            f"{row.controller:20} {row.outcome:8} {row.ticks:5d} {row.collisions:3d} "
            f"{row.infer_ms_p50:7.3f} {row.mean_firing_rate_hz:7.1f} {row.n:4d} {row.e:5d}"
        )
    return "\n".join(lines)
