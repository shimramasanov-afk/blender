"""Frontmost macOS app via AppKit. No HID. No osascript on the hot path."""

from __future__ import annotations

from ctypes import CDLL, c_char_p, c_int32, c_void_p
from dataclasses import dataclass

from l2_brain.experiment.clocks import mono_ns

PARALLELS_BUNDLES = ("com.parallels.desktop.console",)

_objc: CDLL | None = None
_ready = False


@dataclass(frozen=True, slots=True)
class FrontmostApp:
    bundle_id: str
    pid: int
    backend: str = "nsworkspace"


def _sel(objc: CDLL, name: bytes) -> int:
    objc.sel_registerName.restype = c_void_p
    objc.sel_registerName.argtypes = [c_char_p]
    return int(objc.sel_registerName(name) or 0)


def _cls(objc: CDLL, name: bytes) -> int:
    objc.objc_getClass.restype = c_void_p
    objc.objc_getClass.argtypes = [c_char_p]
    return int(objc.objc_getClass(name) or 0)


def _msg(objc: CDLL, obj: int, sel: int, restype=c_void_p):
    objc.objc_msgSend.restype = restype
    objc.objc_msgSend.argtypes = [c_void_p, c_void_p]
    return objc.objc_msgSend(c_void_p(obj), c_void_p(sel))


def _ensure_objc() -> CDLL | None:
    global _objc, _ready
    if _ready:
        return _objc
    _ready = True
    try:
        CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
        _objc = CDLL("/usr/lib/libobjc.A.dylib")
    except OSError:
        _objc = None
    return _objc


def frontmost_app() -> FrontmostApp | None:
    objc = _ensure_objc()
    if objc is None:
        return None
    workspace_cls = _cls(objc, b"NSWorkspace")
    if not workspace_cls:
        return None
    shared = _msg(objc, workspace_cls, _sel(objc, b"sharedWorkspace"))
    if not shared:
        return None
    app = _msg(objc, int(shared), _sel(objc, b"frontmostApplication"))
    if not app:
        return None
    pid = int(_msg(objc, int(app), _sel(objc, b"processIdentifier"), restype=c_int32))
    bundle_ns = _msg(objc, int(app), _sel(objc, b"bundleIdentifier"))
    bundle = ""
    if bundle_ns:
        raw = _msg(objc, int(bundle_ns), _sel(objc, b"UTF8String"), restype=c_char_p)
        if raw:
            bundle = raw.decode("utf-8", errors="replace")
    return FrontmostApp(bundle_id=bundle, pid=pid, backend="nsworkspace")


def is_allowed_frontmost(
    allowed_bundles: tuple[str, ...] = PARALLELS_BUNDLES,
    *,
    target_pid: int | None = None,
) -> bool:
    info = frontmost_app()
    if info is None:
        return False
    if info.bundle_id not in allowed_bundles:
        return False
    if target_pid is not None and target_pid > 0 and info.pid != target_pid:
        return False
    return True


def bench_focus(*, repeats: int = 80, warmup: int = 12) -> dict[str, float | int | str | None]:
    sample = frontmost_app()
    for _ in range(max(0, warmup)):
        frontmost_app()
    times: list[float] = []
    for _ in range(max(1, repeats)):
        t0 = mono_ns()
        frontmost_app()
        times.append((mono_ns() - t0) / 1_000_000.0)
    ordered = sorted(times)
    def pct(q: float) -> float:
        if not ordered:
            return 0.0
        idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
        return float(ordered[idx])
    return {
        "backend": sample.backend if sample else "none",
        "bundle_id": sample.bundle_id if sample else None,
        "pid": sample.pid if sample else None,
        "n": len(times),
        "warmup": warmup,
        "p50_ms": pct(0.50),
        "p95_ms": pct(0.95),
        "max_ms": float(ordered[-1]) if ordered else 0.0,
        "osascript": False,
    }
