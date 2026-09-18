from __future__ import annotations

import pytest

from l2_brain.bench.mps_audit import compare_matmul, numerical_match, probe_ops, run_audit, torch_status


def test_audit_does_not_enable_mps_backend() -> None:
    from l2_brain.accel import selected_backend

    payload = run_audit(steps=5)
    assert selected_backend() == "numpy_cpu"
    assert payload["keep_numpy_cpu"] is True
    assert payload["optimized"] is False


def test_ops_and_status_are_explicit() -> None:
    status = torch_status()
    ops = probe_ops()
    names = {row["op"] for row in ops}
    assert names == {"sparse_mm", "gather", "scatter"}
    if not status["installed"]:
        assert all(row["ok"] is False for row in ops)


@pytest.mark.skipif(not torch_status()["mps_available"], reason="MPS or torch missing")
def test_sparse_and_index_ops_recorded() -> None:
    ops = {row["op"]: row for row in probe_ops()}
    assert "error" in ops["sparse_mm"]


@pytest.mark.skipif(not torch_status()["mps_available"], reason="MPS or torch missing")
def test_matmul_cpu_vs_mps_synced() -> None:
    gemm = compare_matmul(steps=40, sizes=(64,), batches=(1, 32))
    assert gemm["ran"] is True
    b1 = next(row for row in gemm["rows"] if row["batch"] == 1)
    assert b1["synced"] is True
    assert b1["cpu_p50_ms"] > 0.0
    assert b1["mps_p50_ms"] > 0.0


@pytest.mark.skipif(not torch_status()["mps_available"], reason="MPS or torch missing")
def test_cpu_mps_numerics_rtol() -> None:
    result = numerical_match(n=64, rtol=1e-4)
    assert result["ran"] is True
    assert result["finite"] is True
    assert result["ok"] is True
