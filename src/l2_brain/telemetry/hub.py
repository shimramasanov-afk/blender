from __future__ import annotations

from collections import deque
from typing import TypeVar

from l2_brain.experiment.clocks import mono_ns
from l2_brain.telemetry.events import CombatEvent

T = TypeVar("T", bound=CombatEvent)


class TelemetryHub:
    """Bounded tactical bus. Not packet capture. Not process memory."""

    def __init__(self, maxlen: int = 64) -> None:
        if maxlen < 1:
            raise ValueError("maxlen must be >= 1")
        self.maxlen = maxlen
        self._buf: deque[CombatEvent] = deque(maxlen=maxlen)

    def publish(self, event: CombatEvent) -> None:
        self._buf.append(event)

    def get_latest(self, event_type: type[T]) -> T | None:
        for item in reversed(self._buf):
            if isinstance(item, event_type):
                return item
        return None

    def clear(self) -> None:
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)

    def is_stale(self, event: CombatEvent, threshold_ms: int = 300, now_ns: int | None = None) -> bool:
        now = mono_ns() if now_ns is None else now_ns
        return (now - event.timestamp_ns) / 1_000_000.0 > threshold_ms
