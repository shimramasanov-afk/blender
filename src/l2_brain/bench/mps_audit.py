"""Read-only MPS probe. Does not rewrite SNN/GRU or enable accel.py."""

from __future__ import annotations

from typing import Any

from l2_brain.experiment.clocks import mono_ns
from l2_brain.metrics import percentile


def torch_status() -> dict[str, Any]:
    try:
        import torch
    except ImportError:
        return {"installed": False, "mps_available": False, "version": None, "reason": "torch_not_installed"}
    mps = bool(hasattr(torch.backends, "mps") and torch.backends.mps.is_available())
    return {
        "installed": True,
        "mps_available": mps,
        "version": str(torch.__version__),
        "reason": "ok" if mps else "mps_unavailable",
    }


def _try_op(name: str, fn) -> dict[str, Any]:
    try:
        import torch

        fn(torch)
        if torch.backends.mps.is_available():
            torch.mps.synchronize()
        return {"op": name, "ok": True, "error": None}
    except Exception as exc:  # noqa: BLE001 — audit must record the failure
        return {"op": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


def probe_ops() -> list[dict[str, Any]]:
    status = torch_status()
    if not status["installed"] or not status["mps_available"]:
        return [
            {"op": "sparse_mm", "ok": False, "error": status["reason"]},
            {"op": "gather", "ok": False, "error": status["reason"]},
            {"op": "scatter", "ok": False, "error": status["reason"]},
        ]

    def sparse_mm(torch: Any) -> None:
        idx = torch.tensor([[0, 1], [0, 1]], device="mps")
        val = torch.tensor([1.0, 1.0], device="mps")
        sparse = torch.sparse_coo_tensor(idx, val, (2, 2), device="mps")
        _ = torch.sparse.mm(sparse, torch.eye(2, device="mps"))

    def gather(torch: Any) -> None:
        src = torch.arange(8, device="mps", dtype=torch.float32).reshape(2, 4)
        index = torch.tensor([[0, 2], [1, 3]], device="mps")
        _ = torch.gather(src, 1, index)

    def scatter(torch: Any) -> None:
        dest = torch.zeros(2, 4, device="mps")
        index = torch.tensor([[0, 2], [1, 3]], device="mps")
        src = torch.ones(2, 2, device="mps")
        dest.scatter_(1, index, src)

    return [_try_op("sparse_mm", sparse_mm), _try_op("gather", gather), _try_op("scatter", scatter)]


def _matmul_loop(torch: Any, device: str, n: int, batch: int, steps: int) -> list[float]:
    a = torch.randn(batch, n, n, device=device, dtype=torch.float32)
    b = torch.randn(batch, n, n, device=device, dtype=torch.float32)
    sync = device == "mps"
    samples: list[float] = []
    for _ in range(20):
        _ = torch.matmul(a, b)
        if sync:
            torch.mps.synchronize()
    for _ in range(steps):
        t0 = mono_ns()
        _ = torch.matmul(a, b)
        if sync:
            torch.mps.synchronize()
        samples.append((mono_ns() - t0) / 1_000_000.0)
    return samples


def compare_matmul(*, steps: int = 200, sizes: tuple[int, ...] = (64, 128), batches: tuple[int, ...] = (1, 8, 32, 64)) -> dict[str, Any]:
    status = torch_status()
    if not status["installed"] or not status["mps_available"]:
        return {"ran": False, "reason": status["reason"], "rows": []}
    import torch

    rows: list[dict[str, Any]] = []
    crossover: dict[str, int | None] = {}
    for n in sizes:
        first_faster: int | None = None
        for batch in batches:
            cpu = _matmul_loop(torch, "cpu", n, batch, steps)
            mps = _matmul_loop(torch, "mps", n, batch, steps)
            cpu_p50 = float(percentile(cpu, 0.50))
            mps_p50 = float(percentile(mps, 0.50))
            faster = "mps" if mps_p50 < cpu_p50 else "cpu"
            if faster == "mps" and first_faster is None:
                first_faster = batch
            rows.append(
                {
                    "n": n,
                    "batch": batch,
                    "cpu_p50_ms": cpu_p50,
                    "mps_p50_ms": mps_p50,
                    "faster": faster,
                    "synced": True,
                    "steps": steps,
                }
            )
        crossover[f"n{n}"] = first_faster
    return {"ran": True, "reason": "ok", "crossover_batch": crossover, "rows": rows}


def numerical_match(*, n: int = 64, rtol: float = 1e-4) -> dict[str, Any]:
    status = torch_status()
    if not status["installed"] or not status["mps_available"]:
        return {"ran": False, "ok": False, "reason": status["reason"]}
    import torch

    torch.manual_seed(0)
    a = torch.randn(n, n, dtype=torch.float32)
    b = torch.randn(n, n, dtype=torch.float32)
    cpu = torch.matmul(a, b)
    mps = torch.matmul(a.to("mps"), b.to("mps"))
    torch.mps.synchronize()
    ok = bool(torch.allclose(cpu, mps.cpu(), rtol=rtol, atol=1e-5))
    max_abs = float((cpu - mps.cpu()).abs().max())
    finite = bool(torch.isfinite(mps).all().item())
    return {"ran": True, "ok": ok and finite, "max_abs": max_abs, "rtol": rtol, "finite": finite, "reason": "ok"}


def run_audit(*, steps: int = 200) -> dict[str, Any]:
    status = torch_status()
    ops = probe_ops()
    gemm = compare_matmul(steps=steps)
    numerics = numerical_match()
    b1 = next((row for row in gemm.get("rows", []) if row["n"] == 64 and row["batch"] == 1), None)
    mps_faster_b1 = bool(b1 and b1["faster"] == "mps")
    return {
        "torch": status,
        "ops": ops,
        "gemm": gemm,
        "numerics": numerics,
        "mps_faster_at_n64_b1": mps_faster_b1,
        "keep_numpy_cpu": True,
        "optimized": False,
    }
