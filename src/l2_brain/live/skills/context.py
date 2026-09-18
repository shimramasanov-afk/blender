from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from l2_brain.io.cgevent_backend import CGEventInputBackend
from l2_brain.live.perception import PerceptionHub
from l2_brain.telemetry.hub import TelemetryHub


@dataclass
class SkillContext:
    input_backend: CGEventInputBackend | None
    perception: PerceptionHub
    clock: Callable[[], int]
    sleeper: Callable[[float], None]
    telemetry: TelemetryHub | None = None
    window_size: tuple[int, int] | None = None
    log: dict[str, Any] = field(default_factory=dict)
    world_reader: Callable[[], Any] | None = None

    @property
    def backend(self) -> CGEventInputBackend:
        if self.input_backend is None:
            raise RuntimeError("no_input_backend")
        return self.input_backend

    def read_world(self) -> Any:
        """Prefer LiveRuntime.observe (capture recover). Fallback: raw hub."""
        if self.world_reader is not None:
            return self.world_reader()
        return self.perception.observe()
