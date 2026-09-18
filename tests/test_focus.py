from l2_brain.io.focus import bench_focus, frontmost_app


def test_frontmost_app_native() -> None:
    info = frontmost_app()
    assert info is not None
    assert info.pid > 0
    assert info.backend == "nsworkspace"
    assert info.bundle_id


def test_focus_bench_under_2ms() -> None:
    payload = bench_focus(repeats=40, warmup=15)
    assert payload["osascript"] is False
    assert float(payload["p50_ms"]) < 2.0
    assert float(payload["p95_ms"]) < 5.0


def test_focus_does_not_spawn_osascript(monkeypatch) -> None:
    import subprocess

    def boom(*_a, **_k):
        raise AssertionError("osascript must not run")

    monkeypatch.setattr(subprocess, "run", boom)
    info = frontmost_app()
    assert info is None or info.pid > 0
