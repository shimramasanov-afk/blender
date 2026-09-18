from __future__ import annotations

from l2_brain.accel import selected_backend
from l2_brain.evaluate import run_suite
from l2_brain.metrics import percentile, summarize


def test_percentile() -> None:
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([10], 0.95) == 10


def test_evaluate_suite_returns_split_metrics() -> None:
    reports = run_suite("reactive", "open_field", episodes=3, seed=0)
    row = summarize(reports)
    assert row["episodes"] == 3
    assert row["success_rate"] >= 0.6
    assert float(row["p95_loop_ms"]) >= float(row["p95_infer_ms"])
    assert selected_backend() == "numpy_cpu"
