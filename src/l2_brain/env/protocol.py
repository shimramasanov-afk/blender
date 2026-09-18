from __future__ import annotations

from typing import Protocol

from l2_brain.types import Action, Observation, StepInfo


class Environment(Protocol):
    def reset(self, seed: int | None = None) -> Observation: ...

    def step(self, action: Action) -> tuple[Observation, StepInfo]: ...

    def close(self) -> None: ...
