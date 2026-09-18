from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.control.baseline import BaselineController
from l2_brain.control.config import BaselineConfig
from l2_brain.control.eval import run_episode
from l2_brain.control.gru import GRUConfig, GRUController
from l2_brain.control.snn import LIFConfig, SNNController
from l2_brain.experiment.clocks import mono_ns
from l2_brain.sim.config import catalog

CONTROLLERS = ("baseline_v1", "baseline_memory_v1", "gru_v1", "snn_v1")


@dataclass(frozen=True, slots=True)
class BenchRow:
    controller: str
    episode_id: str
    outcome: str
    success: bool
    ticks: int
    collisions: int
    n_params: int
    param_kind: str
    state_floats: int
    k_substeps: int
    infer_ms_p50: float
    infer_ms_p95: float
    learned: bool = False
    transfer_claim: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _TimedController:
    def __init__(self, inner: object) -> None:
        self.inner = inner
        self.infer_ms: list[float] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def step(self, observation: object, now_ns: int, intent_ttl_ns: int) -> object:
        t0 = mono_ns()
        intent = self.inner.step(observation, now_ns, intent_ttl_ns)
        self.infer_ms.append((mono_ns() - t0) / 1_000_000.0)
        return intent


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    return float(np.quantile(np.asarray(values, dtype=np.float64), q))


def _count_numbers(payload: dict[str, Any]) -> int:
    n = 0
    for value in payload.values():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            n += 1
    return n


def accounting(name: str, controller: object) -> dict[str, int]:
    if name.startswith("baseline"):
        cfg = getattr(controller, "_config", BaselineConfig())
        return {
            "n_params": _count_numbers(cfg.to_dict()),
            "param_kind": "heuristic_knobs",
            "state_floats": 4 if name == "baseline_v1" else 8,
            "k_substeps": 1,
        }
    if name == "gru_v1":
        hidden = int(getattr(controller, "config").hidden)
        return {
            "n_params": int(controller.n_params()),
            "param_kind": "dense_weights",
            "state_floats": hidden,
            "k_substeps": 1,
        }
    if name == "snn_v1":
        return {
            "n_params": int(controller.n_params()),
            "param_kind": "dense_stored_weights",
            "state_floats": int(2 * controller.config.n),
            "k_substeps": int(controller.config.steps_per_tick),
        }
    raise ValueError(f"unknown controller {name}")


def build_controller(name: str, *, seed: int = 0) -> object:
    if name == "baseline_v1":
        return BaselineController(BaselineConfig(recovery=False))
    if name == "baseline_memory_v1":
        return BaselineController(BaselineConfig(recovery=True))
    if name == "gru_v1":
        return GRUController(GRUConfig(seed=seed, with_memory=True))
    if name == "snn_v1":
        return SNNController(LIFConfig(seed=seed))
    raise ValueError(f"unknown controller {name}")


def run_bench(
    *,
    scenario: str = "open_goal",
    split: str = "training",
    variant: int = 0,
    seed: int = 0,
    names: tuple[str, ...] = CONTROLLERS,
) -> list[BenchRow]:
    spec = next(
        item
        for item in catalog(seed, suite="frozen")
        if item.scenario == scenario and item.split == split and item.variant == variant
    )
    rows: list[BenchRow] = []
    for name in names:
        inner = build_controller(name, seed=seed)
        timed = _TimedController(inner)
        episode, _result = run_episode(spec, controller=timed)
        acc = accounting(name, inner)
        rows.append(
            BenchRow(
                controller=name,
                episode_id=episode.episode_id,
                outcome=episode.outcome,
                success=episode.success,
                ticks=episode.ticks,
                collisions=episode.collisions,
                n_params=acc["n_params"],
                param_kind=str(acc["param_kind"]),
                state_floats=acc["state_floats"],
                k_substeps=acc["k_substeps"],
                infer_ms_p50=_percentile(timed.infer_ms, 0.50),
                infer_ms_p95=_percentile(timed.infer_ms, 0.95),
            )
        )
    return rows


def write_bench(path: Path, rows: list[BenchRow], *, extras: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "suite": "nav-sim-v1-mini",
        "hypothesis": "On one open-field episode, four controllers can be compared on resources and outcome. Not Frozen 60. Not H3/H4.",
        "reject_if": "A controller raises, yields no MotorIntent, or this table is published as catalog superiority.",
        "n_runs": 1,
        "why_one_run": "Hod 26 mini-set: single frozen episode, seed=0. Not a multi-seed claim.",
        "learned": False,
        "transfer_claim": False,
        "biological_claim": False,
        "rows": [row.to_dict() for row in rows],
        "extras": extras or {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def format_table(rows: list[BenchRow]) -> str:
    header = (
        f"{'controller':22} {'out':8} {'ticks':>5} {'col':>3} "
        f"{'params':>7} {'state':>6} {'K':>3} {'p50ms':>7} {'p95ms':>7}"
    )
    lines = [header]
    for row in rows:
        lines.append(
            f"{row.controller:22} {row.outcome:8} {row.ticks:5d} {row.collisions:3d} "
            f"{row.n_params:7d} {row.state_floats:6d} {row.k_substeps:3d} "
            f"{row.infer_ms_p50:7.3f} {row.infer_ms_p95:7.3f}"
        )
    return "\n".join(lines)
