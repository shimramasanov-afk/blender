from __future__ import annotations

from l2_brain.safety import LIVE_CLIENT_BLOCKED_REASON
from l2_brain.types import Action, Observation, StepInfo


class LiveClientEnv:
    """Real client is out of scope until S4."""

    def reset(self, seed: int | None = None) -> Observation:
        raise NotImplementedError(LIVE_CLIENT_BLOCKED_REASON)

    def step(self, action: Action) -> tuple[Observation, StepInfo]:
        raise NotImplementedError(LIVE_CLIENT_BLOCKED_REASON)

    def close(self) -> None:
        return None
