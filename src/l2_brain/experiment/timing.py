from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from l2_brain.experiment.clocks import mono_ns
from l2_brain.metrics import percentile

T = TypeVar("T")

STAGE_NAMES = (
    "wait_frame_ms",
    "frame_age_ms",
    "encode_ms",
    "infer_ms",
    "decode_ms",
    "act_ms",
    "wait_effect_ms",
)


@dataclass(frozen=True, slots=True)
class SeriesReport:
    p50: float
    p95: float
    p99: float
    n: int
    unit: str

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "p50": self.p50,
            "p95": self.p95,
            "p99": self.p99,
            "n": self.n,
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class SyncResult:
    ok: bool
    backend: str
    reason: str


@dataclass(frozen=True, slots=True)
class ComputeMeasurement:
    elapsed_ms: float
    synced: bool
    is_compute: bool
    reason: str
    value: Any = None


@dataclass
class TimingAccumulator:
    samples: dict[str, list[float]] = field(default_factory=dict)

    def add(self, name: str, value: float | None) -> None:
        if value is None:
            return
        self.samples.setdefault(name, []).append(float(value))

    def report(self) -> dict[str, dict[str, float | int | str]]:
        out: dict[str, dict[str, float | int | str]] = {}
        names = list(STAGE_NAMES) + [k for k in self.samples if k not in STAGE_NAMES]
        for name in names:
            values = self.samples.get(name, [])
            out[name] = summarize_series(values, unit="ms").to_dict()
        return out


def summarize_series(values: list[float], *, unit: str = "ms") -> SeriesReport:
    return SeriesReport(
        p50=percentile(values, 0.50),
        p95=percentile(values, 0.95),
        p99=percentile(values, 0.99),
        n=len(values),
        unit=unit,
    )


def gpu_synchronize() -> SyncResult:
    """Block until submitted GPU work finishes. Missing backend is not a sync."""
    try:
        import torch
    except ImportError:
        return SyncResult(False, "none", "torch_not_installed")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        torch.mps.synchronize()
        return SyncResult(True, "mps", "ok")
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        return SyncResult(True, "cuda", "ok")
    return SyncResult(False, "torch", "no_gpu_device")


def measure_compute(
    fn: Callable[[], T],
    *,
    require_gpu_sync: bool = False,
) -> ComputeMeasurement:
    """Elapsed time is compute only if the device was synchronized.

    Returning from an asynchronous GPU launch is not compute time.
    """
    if require_gpu_sync:
        before = gpu_synchronize()
        if not before.ok:
            started = mono_ns()
            value = fn()
            elapsed = (mono_ns() - started) / 1_000_000.0
            return ComputeMeasurement(
                elapsed_ms=elapsed,
                synced=False,
                is_compute=False,
                reason=before.reason,
                value=value,
            )
        started = mono_ns()
        value = fn()
        after = gpu_synchronize()
        elapsed = (mono_ns() - started) / 1_000_000.0
        return ComputeMeasurement(
            elapsed_ms=elapsed,
            synced=after.ok,
            is_compute=after.ok,
            reason=after.reason,
            value=value,
        )
    started = mono_ns()
    value = fn()
    elapsed = (mono_ns() - started) / 1_000_000.0
    return ComputeMeasurement(
        elapsed_ms=elapsed,
        synced=True,
        is_compute=True,
        reason="cpu",
        value=value,
    )


def bench_single_step_latency(
    fn: Callable[[], Any],
    *,
    n: int,
    require_gpu_sync: bool = False,
) -> SeriesReport:
    """One call per sample. GPU path synchronizes each step when requested."""
    if n < 1:
        raise ValueError("n must be >= 1")
    samples: list[float] = []
    for _ in range(n):
        measured = measure_compute(fn, require_gpu_sync=require_gpu_sync)
        if require_gpu_sync and not measured.is_compute:
            raise RuntimeError(
                f"GPU latency bench refused unsynced timing: {measured.reason}"
            )
        samples.append(measured.elapsed_ms)
    return summarize_series(samples, unit="ms")


def bench_throughput(
    fn: Callable[[], Any],
    *,
    n: int,
    require_gpu_sync: bool = False,
) -> dict[str, float | int | str | bool]:
    """Tight loop. Reports items/s, not single-step latency."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if require_gpu_sync:
        sync = gpu_synchronize()
        if not sync.ok:
            raise RuntimeError(f"GPU throughput bench needs sync: {sync.reason}")
    started = mono_ns()
    for _ in range(n):
        fn()
    if require_gpu_sync:
        gpu_synchronize()
    elapsed_s = (mono_ns() - started) / 1_000_000_000.0
    return {
        "kind": "throughput",
        "n": n,
        "elapsed_s": elapsed_s,
        "items_per_s": n / elapsed_s if elapsed_s > 0 else 0.0,
        "gpu_synced": require_gpu_sync,
        "not_latency": True,
    }
