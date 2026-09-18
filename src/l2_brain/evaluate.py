from __future__ import annotations

import argparse
import json
from pathlib import Path

from l2_brain.config import CONTROLLERS, SCENARIOS
from l2_brain.controllers import make_controller
from l2_brain.env.synthetic import SyntheticEnv
from l2_brain.loop import ControlLoop
from l2_brain.metrics import summarize
from l2_brain.types import EpisodeReport


def run_suite(
    controller_name: str,
    scenario: str,
    episodes: int,
    seed: int,
) -> list[EpisodeReport]:
    reports: list[EpisodeReport] = []
    for offset in range(episodes):
        env = SyntheticEnv(scenario=scenario)
        controller = make_controller(controller_name)
        reports.append(ControlLoop(env, controller).run_episode(seed + offset))
    return reports


def format_summary(row: dict[str, float | int | str]) -> str:
    return (
        f"{row['controller']:10} {row['scenario']:13} "
        f"success={float(row['success_rate']):.2f} "
        f"stuck={float(row['stuck_rate']):.2f} "
        f"infer_ms={float(row['mean_infer_ms']):.3f} "
        f"loop_ms={float(row['mean_loop_ms']):.3f} "
        f"infer/loop_p95={float(row['infer_over_loop_p95']):.3f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сравнение контроллеров на синтетическом стенде")
    parser.add_argument("--controller", choices=CONTROLLERS, default="reactive")
    parser.add_argument("--scenario", choices=SCENARIOS, default="open_field")
    parser.add_argument("--episodes", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--all-controllers", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    names = CONTROLLERS if args.all_controllers else (args.controller,)
    rows = []
    for name in names:
        reports = run_suite(name, args.scenario, args.episodes, args.seed)
        row = summarize(reports)
        rows.append(row)
        print(format_summary(row))

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
