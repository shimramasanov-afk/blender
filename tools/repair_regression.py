"""Repeat the six training probes; not a full catalog or held-out evaluation.

Run from the project root: .venv/bin/python tools/repair_regression.py OUTPUT.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform

from l2_brain.control.config import BaselineConfig
from l2_brain.control.eval import run_episode
from l2_brain.sim.config import EpisodeSpec

SCENES = ("open_goal", "narrow_gate", "corridor", "vanishing_target",
          "latency_drops", "single_obstacle")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; choose a new path to preserve evidence.")
    root = Path(__file__).resolve().parents[1]
    config = BaselineConfig(recovery=False)
    rows = []
    hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted((root / "src").rglob("*.py"))}
    for scene in SCENES:
        row, _ = run_episode(EpisodeSpec(scene, "training", 0, 0), config=config)
        rows.append(row.to_dict())
        print(f"{scene}: success={row.success}, ticks={row.ticks}, collisions={row.collisions}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "scope": "six training v0 seed=0 probes, max_steps=200; no statistical or transfer claim",
        "metrics_version": "repair-20260917",
        "recovery_time_unit": "seconds",
        "python": platform.python_version(),
        "source_sha256": hashes,
        "controller_config": config.to_dict(),
        "episodes": rows,
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
