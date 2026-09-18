from __future__ import annotations

from l2_brain.features import extract
from l2_brain.types import Action, Observation


class ReactiveController:
    """No memory. Turns toward current red mass or slowly scans right."""

    name = "reactive"

    def reset(self, seed: int | None = None) -> None:
        return None

    def step(self, observation: Observation) -> Action:
        feat = extract(observation)
        if not feat.seen:
            return Action(turn=0.35, forward=0.0, engage=0.0)
        assert feat.centroid is not None
        offset = feat.centroid - 0.5
        if feat.mass > 0.045 and abs(offset) < 0.08:
            return Action(turn=0.0, forward=0.15, engage=1.0)
        if abs(offset) < 0.06:
            return Action(turn=0.0, forward=1.0, engage=0.0)
        return Action(turn=float(max(-1.0, min(1.0, offset * 3.2))), forward=0.25, engage=0.0)
