from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class CircuitConfig:
    seed: int = 0
    ticks: int = 32
    tick_hz: int = 20
    frame_h: int = 64
    frame_w: int = 64
    max_intent_age_ns: int = 100_000_000
    stale_frame_ns: int = 250_000_000
    source_id: str = "mock.blob"
    record_path: Path | None = None
    log_level: str = "INFO"
    strafe_supported: bool = False
    now_ns: Callable[[], int] | None = None
    keep_frames: str = "none"
    frame_every: int = 1
    writer_bound: int = 128
    model_version: str = "feature_reactive:default"
    gpu_sync: bool = False
    encoder_name: str = "color_blob"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.ticks < 1:
            raise ValueError("ticks must be >= 1")
        if self.tick_hz < 1:
            raise ValueError("tick_hz must be >= 1")
        if self.frame_h < 8 or self.frame_w < 8:
            raise ValueError("frame size must be >= 8")
        if self.max_intent_age_ns <= 0 or self.stale_frame_ns <= 0:
            raise ValueError("timeouts must be positive")
        if self.log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError(f"bad log_level {self.log_level!r}")
        if self.keep_frames not in {"none", "all", "every"}:
            raise ValueError(f"bad keep_frames {self.keep_frames!r}")
        if self.frame_every < 1 or self.writer_bound < 1:
            raise ValueError("frame_every and writer_bound must be >= 1")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> CircuitConfig:
        known = {k: data[k] for k in data if k in cls.__dataclass_fields__}
        if "record_path" in known and known["record_path"] is not None:
            known["record_path"] = Path(known["record_path"])
        return cls(**known)

    @classmethod
    def from_json_path(cls, path: Path) -> CircuitConfig:
        return cls.from_mapping(json.loads(path.read_text(encoding="utf-8")))
