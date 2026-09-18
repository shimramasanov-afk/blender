from __future__ import annotations

from typing import Protocol

from l2_brain.types import Action


class Actuator(Protocol):
    def apply(self, action: Action) -> None: ...

    def emergency_stop(self) -> None: ...
