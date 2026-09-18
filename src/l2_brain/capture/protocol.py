from __future__ import annotations

from typing import Protocol

from l2_brain.types import Observation


class FrameSource(Protocol):
    def start(self) -> None: ...

    def latest(self) -> Observation: ...

    def stop(self) -> None: ...
