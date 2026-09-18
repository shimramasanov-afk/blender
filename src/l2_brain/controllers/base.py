from __future__ import annotations

from typing import Protocol

from l2_brain.types import Action, Observation


class Controller(Protocol):
    name: str

    def reset(self, seed: int | None = None) -> None: ...

    def step(self, observation: Observation) -> Action: ...
