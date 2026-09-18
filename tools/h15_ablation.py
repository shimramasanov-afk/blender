"""Closed-loop H15 on the frozen catalog. Does not overwrite F14/F15.

Run from the project root: .venv/bin/python tools/h15_ablation.py docs/evidence/h15
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from l2_brain.control.config import BaselineConfig
from l2_brain.control.eval import run_catalog, write_report

HYPOTHESIS = (
    "On the frozen nav-sim-v1 catalog seed=0, Observation.navigation raises "
    "success by at least 0.15 versus the same controller with color_blob only."
)
REJECT = "Delta success_rate < 0.15 on the same 60 episodes."

VARIANTS: tuple[tuple[str, str, str], ...] = (
    ("blob", "color_blob", "all"),
    ("target", "navigation_v1", "target"),
    ("target_flow", "navigation_v1", "target_flow"),
    ("target_expansion", "navigation_v1", "target_expansion"),
    ("all", "navigation_v1", "all"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()
    out_dir: Path = args.out_dir
    summary_path = out_dir / "summary.json"
    if summary_path.exists():
        parser.error("summary.json exists; choose a new directory to preserve evidence.")
    out_dir.mkdir(parents=True, exist_ok=True)
    arms: list[dict] = []
    for name, encoder_name, channels in VARIANTS:
        path = out_dir / f"{name}.json"
        if path.exists():
            prior = json.loads(path.read_text(encoding="utf-8"))
            n = int(prior.get("summary", {}).get("n", 0))
            successes = int(prior.get("summary", {}).get("successes", 0))
            print(f"skip {name}: {successes}/{n} already written", flush=True)
            arms.append(
                {
                    "name": name,
                    "encoder": encoder_name,
                    "channels": name,
                    "n": n,
                    "successes": successes,
                    "success_rate": successes / n if n else 0.0,
                    "outcomes": prior.get("summary", {}).get("outcomes", {}),
                    "causes": prior.get("summary", {}).get("causes", {}),
                    "path": str(path),
                    "resumed": True,
                }
            )
            continue
        config = BaselineConfig(recovery=True, channels=channels if encoder_name != "color_blob" else "all")
        print(f"start {name} encoder={encoder_name} channels={config.channels}", flush=True)
        rows = run_catalog(0, config=config, suite="frozen", encoder_name=encoder_name)
        extras = {
            "suite": "frozen",
            "seed": 0,
            "controller": "baseline_memory_v1",
            "encoder_name": encoder_name,
            "channels": name,
            "held_out_used_for_tuning": False,
            "held_out_independent": False,
            "biological_claim": False,
            "replaces_f14": False,
            "hypothesis": HYPOTHESIS,
            "reject_if": REJECT,
            "config": config.to_dict(),
        }
        payload = write_report(path, rows, extras=extras)
        arm = {
            "name": name,
            "encoder": encoder_name,
            "channels": name,
            "n": payload["summary"]["n"],
            "successes": payload["summary"]["successes"],
            "success_rate": payload["summary"]["successes"] / payload["summary"]["n"],
            "outcomes": payload["summary"]["outcomes"],
            "causes": payload["summary"]["causes"],
            "path": str(path),
        }
        arms.append(arm)
        print(
            f"done {name}: {arm['successes']}/{arm['n']} {arm['outcomes']}",
            flush=True,
        )
    blob = next(item for item in arms if item["name"] == "blob")
    compared = []
    for arm in arms:
        if arm["name"] == "blob":
            continue
        delta = arm["success_rate"] - blob["success_rate"]
        compared.append(
            {
                "name": arm["name"],
                "successes": arm["successes"],
                "delta_success_rate": delta,
                "meets_h15": delta >= 0.15,
            }
        )
    nav = next(item for item in compared if item["name"] == "all")
    summary = {
        "hypothesis": HYPOTHESIS,
        "reject_if": REJECT,
        "metrics_version": "repair-20260917",
        "suite": "nav-sim-v1",
        "seed": 0,
        "replicas": 1,
        "replica_reason": "same single-catalog protocol as F14/F15",
        "held_out_independent": False,
        "replaces_f14": False,
        "arms": arms,
        "delta_vs_blob": compared,
        "h15_status": "accepted" if nav["meets_h15"] else "rejected",
        "limitation": "synthetic stand; not transfer; not SNN; not a claim that memory is better",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"h15_status": summary["h15_status"], "delta_vs_blob": compared}, indent=2), flush=True)


if __name__ == "__main__":
    main()
