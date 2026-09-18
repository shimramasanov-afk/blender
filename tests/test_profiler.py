from __future__ import annotations

from l2_brain.bench.profiler import profile_controller


def test_profiler_reports_four_stages() -> None:
    row = profile_controller("gru_v1", ticks=4, warmup=1, seed=0)
    assert set(row["stages"]) >= {"t_encode", "t_infer", "t_tactical", "t_decode", "t_tick"}
    assert row["ticks"] == 4
    assert row["hid_sent"] is False
    assert row["stages"]["t_infer"]["n"] == 4
    assert row["stages"]["t_infer"]["p50_ms"] >= 0.0
