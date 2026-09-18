"""Five-controller mini-suite. Not Frozen 60. Controllers are not modified."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.control.baseline import BaselineController
from l2_brain.control.config import BaselineConfig
from l2_brain.control.eval import run_episode
from l2_brain.control.gru import GRUConfig, GRUController
from l2_brain.control.malecns import MaleCNSController
from l2_brain.control.snn import LIFConfig, SNNController
from l2_brain.experiment.clocks import mono_ns
from l2_brain.learning.train import export_rstdp_weights
from l2_brain.sim.config import catalog

CONTROLLERS = (
    "baseline_memory_v1",
    "gru_v1",
    "snn_v1",
    "snn_rstdp",
    "malecns_bio",
)
MINI_SUITE = (
    ("open_goal", "training", 0),
    ("camera_spin", "training", 0),
    ("latency_drops", "training", 0),
    ("vanishing_target", "training", 0),
    ("single_obstacle", "training", 0),
)
RSTDP_WEIGHTS = Path("docs/evidence/hod32/snn_rstdp_w_in.npz")


@dataclass(frozen=True, slots=True)
class SuiteCell:
    controller: str
    episode_id: str
    scenario: str
    outcome: str
    success: bool
    ticks: int
    collisions: int
    infer_ms_p50: float
    infer_ms_p95: float
    k_substeps: int
    n_params: int
    state_floats: int
    direction_changes: int
    mean_progress: float
    path_length: float
    learned: bool

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
    return sum(isinstance(value, (int, float)) and not isinstance(value, bool) for value in payload.values())


def suite_specs(seed: int = 0):
    catalog_rows = catalog(seed, suite="frozen")
    out = []
    for scenario, split, variant in MINI_SUITE:
        out.append(
            next(
                item
                for item in catalog_rows
                if item.scenario == scenario and item.split == split and item.variant == variant
            )
        )
    return out


def ensure_rstdp_weights(path: Path = RSTDP_WEIGHTS, *, seed: int = 0) -> np.ndarray:
    if path.exists():
        payload = np.load(path)
        return np.asarray(payload["w_in"], dtype=np.float64)
    weights = export_rstdp_weights(seed=seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, w_in=weights, w_in_norm=np.linalg.norm(weights))
    return weights


def accounting(name: str, controller: object) -> dict[str, int]:
    if name == "baseline_memory_v1":
        cfg = getattr(controller, "_config", BaselineConfig())
        return {"n_params": _count_numbers(cfg.to_dict()), "state_floats": 8, "k_substeps": 1}
    if name == "gru_v1":
        return {
            "n_params": int(controller.n_params()),
            "state_floats": int(controller.config.hidden),
            "k_substeps": 1,
        }
    if name in {"snn_v1", "snn_rstdp"}:
        return {
            "n_params": int(controller.n_params()),
            "state_floats": int(2 * controller.config.n),
            "k_substeps": int(controller.config.steps_per_tick),
        }
    if name == "malecns_bio":
        return {
            "n_params": int(controller.n_params()),
            "state_floats": int(2 * controller.config.n),
            "k_substeps": int(controller.config.steps_per_tick),
        }
    raise ValueError(f"unknown controller {name}")


def build_controller(name: str, *, seed: int = 0, rstdp_weights: np.ndarray | None = None) -> object:
    if name == "baseline_memory_v1":
        return BaselineController(BaselineConfig(recovery=True))
    if name == "gru_v1":
        return GRUController(GRUConfig(seed=seed, with_memory=True))
    if name == "snn_v1":
        return SNNController(LIFConfig(seed=seed))
    if name == "snn_rstdp":
        ctl = SNNController(LIFConfig(seed=seed))
        ctl.name = "snn_rstdp"
        weights = rstdp_weights if rstdp_weights is not None else ensure_rstdp_weights(seed=seed)
        ctl.initialize()
        ctl._net.w_in = np.asarray(weights, dtype=np.float64).copy()
        return ctl
    if name == "malecns_bio":
        return MaleCNSController("bio", seed=seed)
    raise ValueError(f"unknown controller {name}")


def run_suite(*, seed: int = 0, names: tuple[str, ...] = CONTROLLERS) -> list[SuiteCell]:
    specs = suite_specs(seed)
    rstdp = ensure_rstdp_weights(seed=seed) if "snn_rstdp" in names else None
    cells: list[SuiteCell] = []
    for name in names:
        acc_probe = build_controller(name, seed=seed, rstdp_weights=rstdp)
        acc = accounting(name, acc_probe)
        learned = name == "snn_rstdp"
        for spec in specs:
            inner = build_controller(name, seed=seed, rstdp_weights=rstdp)
            timed = _TimedController(inner)
            episode, result = run_episode(spec, controller=timed)
            cells.append(
                SuiteCell(
                    controller=name,
                    episode_id=episode.episode_id,
                    scenario=spec.scenario,
                    outcome=episode.outcome,
                    success=episode.success,
                    ticks=episode.ticks,
                    collisions=episode.collisions,
                    infer_ms_p50=_percentile(timed.infer_ms, 0.50),
                    infer_ms_p95=_percentile(timed.infer_ms, 0.95),
                    k_substeps=acc["k_substeps"],
                    n_params=acc["n_params"],
                    state_floats=acc["state_floats"],
                    direction_changes=result.direction_changes,
                    mean_progress=result.path_length / max(result.ticks, 1),
                    path_length=result.path_length,
                    learned=learned,
                )
            )
    return cells


def summarize(cells: list[SuiteCell]) -> dict[str, Any]:
    by_name: dict[str, Any] = {}
    for name in CONTROLLERS:
        rows = [cell for cell in cells if cell.controller == name]
        if not rows:
            continue
        by_name[name] = {
            "successes": sum(int(row.success) for row in rows),
            "n": len(rows),
            "infer_ms_p50_mean": float(np.mean([row.infer_ms_p50 for row in rows])),
            "n_params": rows[0].n_params,
            "k_substeps": rows[0].k_substeps,
            "state_floats": rows[0].state_floats,
            "learned": rows[0].learned,
            "outcomes": {row.scenario: row.outcome for row in rows},
            "ticks": {row.scenario: row.ticks for row in rows},
        }
    return by_name


def write_suite(path: Path, cells: list[SuiteCell]) -> dict[str, Any]:
    payload = {
        "suite": "nav-sim-v1-mini5",
        "hypothesis": (
            "On five training:v0:s0 scenes, baseline_memory_v1 has at least as many "
            "successes as gru_v1 / snn_v1 / snn_rstdp / malecns_bio. Among neural "
            "kernels, snn_v1 is the L2 candidate if it is not worse on successes "
            "and stays inside the infer budget. Not Frozen 60. Not H3/H4."
        ),
        "reject_if": (
            "A controller raises, weights of frozen controllers are edited, Frozen 60 "
            "is run, or this table is published as catalog ranking / client readiness."
        ),
        "n_runs": 1,
        "why_one_run": "Hod 32 representative slice, seed=0, one variant per scene.",
        "frozen60": False,
        "transfer_claim": False,
        "h3_claim": False,
        "h4_claim": False,
        "h11_claim": False,
        "scenes": [f"{scene}:training:v0:s0" for scene, _split, _variant in MINI_SUITE],
        "controllers": list(CONTROLLERS),
        "summary": summarize(cells),
        "rows": [cell.to_dict() for cell in cells],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def format_matrix(cells: list[SuiteCell]) -> str:
    scenes = [scene for scene, _split, _variant in MINI_SUITE]
    header = f"{'controller':20} " + " ".join(f"{scene[:12]:>12}" for scene in scenes) + f" {'ok':>4}"
    lines = [header]
    for name in CONTROLLERS:
        rows = [cell for cell in cells if cell.controller == name]
        if not rows:
            continue
        bits = []
        for scene in scenes:
            cell = next(row for row in rows if row.scenario == scene)
            mark = f"{cell.ticks}{'*' if cell.success else '-'}"
            bits.append(f"{mark:>12}")
        ok = sum(int(row.success) for row in rows)
        lines.append(f"{name:20} " + " ".join(bits) + f" {ok:4d}")
    return "\n".join(lines)


def format_summary(payload: dict[str, Any]) -> str:
    header = f"{'controller':20} {'ok/5':>5} {'p50ms':>7} {'params':>7} {'K':>3}"
    lines = [header]
    for name, row in payload["summary"].items():
        lines.append(
            f"{name:20} {row['successes']:2d}/{row['n']:<2d} "
            f"{row['infer_ms_p50_mean']:7.3f} {row['n_params']:7d} {row['k_substeps']:3d}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="l2-brain-suite", description="Mini comparative suite, not Frozen 60")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    cells = run_suite(seed=args.seed)
    payload = write_suite(args.out, cells)
    print(format_matrix(cells))
    print(format_summary(payload))
    print(
        json.dumps(
            {
                "out": str(args.out),
                "successes": {name: row["successes"] for name, row in payload["summary"].items()},
                "frozen60": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
