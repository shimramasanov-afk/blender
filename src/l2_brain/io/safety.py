from __future__ import annotations

from collections.abc import Callable

from l2_brain.experiment.clocks import mono_ns


class InputWatchdog:
    """Releases holds if the controller misses a heartbeat. No OS HID."""

    def __init__(
        self,
        timeout_ms: int = 250,
        *,
        now_ns: Callable[[], int] | None = None,
        on_release: Callable[[tuple[str, ...]], None] | None = None,
    ) -> None:
        if timeout_ms < 1:
            raise ValueError("timeout_ms must be >= 1")
        self.timeout_ms = timeout_ms
        self._now = now_ns or mono_ns
        self._on_timeout = on_release
        self.active_holds: set[str] = set()
        self.last_heartbeat_ns = self._now()
        self.release_count = 0

    def heartbeat(self, now_ns: int | None = None) -> None:
        self.last_heartbeat_ns = int(now_ns if now_ns is not None else self._now())

    def hold(self, key: str) -> None:
        self.active_holds.add(key)

    def release(self, key: str) -> None:
        self.active_holds.discard(key)

    def timed_out(self, now_ns: int | None = None) -> bool:
        now = int(now_ns if now_ns is not None else self._now())
        return (now - self.last_heartbeat_ns) / 1_000_000.0 > self.timeout_ms

    def check(self, now_ns: int | None = None) -> bool:
        if self.timed_out(now_ns) and self.active_holds:
            held = self.release_all()
            if held and self._on_timeout is not None:
                self._on_timeout(held)
            return True
        return False

    def release_all(self) -> tuple[str, ...]:
        held = tuple(sorted(self.active_holds))
        self.active_holds.clear()
        if held:
            self.release_count += 1
        return held
