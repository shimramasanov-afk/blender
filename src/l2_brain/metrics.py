from __future__ import annotations

import math

from l2_brain.types import EpisodeReport


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def summarize(reports: list[EpisodeReport]) -> dict[str, float | int | str]:
    infer = [ms for report in reports for ms in report.infer_ms]
    loop = [ms for report in reports for ms in report.loop_ms]
    n = len(reports)
    success = sum(1 for report in reports if report.success)
    stuck = sum(1 for report in reports if report.stuck)
    infer_p95 = percentile(infer, 0.95)
    loop_p95 = percentile(loop, 0.95)
    return {
        "controller": reports[0].controller if reports else "",
        "scenario": reports[0].scenario if reports else "",
        "episodes": n,
        "success_rate": success / n if n else 0.0,
        "stuck_rate": stuck / n if n else 0.0,
        "mean_ticks": (sum(r.ticks for r in reports) / n) if n else 0.0,
        "mean_infer_ms": (sum(infer) / len(infer)) if infer else 0.0,
        "mean_loop_ms": (sum(loop) / len(loop)) if loop else 0.0,
        "p95_infer_ms": infer_p95,
        "p95_loop_ms": loop_p95,
        "infer_over_loop_p95": (infer_p95 / loop_p95) if loop_p95 else 0.0,
    }
