from l2_brain.bench.mps_audit import run_audit, torch_status
from l2_brain.bench.profiler import run_profile, write_profile

__all__ = ["run_audit", "run_profile", "run_suite", "torch_status", "write_profile", "write_suite"]


def __getattr__(name: str):
    if name in {"run_suite", "write_suite"}:
        from l2_brain.bench.suite_runner import run_suite, write_suite

        return {"run_suite": run_suite, "write_suite": write_suite}[name]
    raise AttributeError(name)
