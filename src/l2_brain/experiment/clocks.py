from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

ClockId = Literal["mono", "event", "device"]


class ClockMismatch(ValueError):
    """Raised when two timestamps from different clocks are subtracted."""


@dataclass(frozen=True, slots=True)
class Timestamp:
    value_ns: int
    clock: ClockId


@dataclass(frozen=True, slots=True)
class ClockOffset:
    """Explicit conversion between two clock domains. Never inferred."""

    source: ClockId
    target: ClockId
    add_ns: int


def mono_ns() -> int:
    return time.perf_counter_ns()


def event_ns() -> int:
    return time.time_ns()


def stamp(value_ns: int, clock: ClockId) -> Timestamp:
    return Timestamp(int(value_ns), clock)


def interval_ns(start: Timestamp, end: Timestamp) -> int:
    if start.clock != end.clock:
        raise ClockMismatch(
            f"cannot subtract {end.clock} from {start.clock} without convert()"
        )
    return end.value_ns - start.value_ns


def interval_ms(start: Timestamp, end: Timestamp) -> float:
    return interval_ns(start, end) / 1_000_000.0


def convert(ts: Timestamp, offset: ClockOffset) -> Timestamp:
    if ts.clock != offset.source:
        raise ClockMismatch(
            f"offset source is {offset.source}, timestamp clock is {ts.clock}"
        )
    return Timestamp(ts.value_ns + offset.add_ns, offset.target)
