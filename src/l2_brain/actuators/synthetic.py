from __future__ import annotations

from l2_brain.env.synthetic import SyntheticEnv
from l2_brain.types import Action


class SyntheticActuator:
    """Stand-in for the Actuator protocol. Physics stays in Environment.step."""

    def __init__(self, env: SyntheticEnv) -> None:
        self._env = env
        self.last: Action | None = None

    def apply(self, action: Action) -> None:
        self.last = action.clipped()

    def emergency_stop(self) -> None:
        self.last = Action(turn=0.0, forward=0.0, engage=0.0)
        self._env.close()
