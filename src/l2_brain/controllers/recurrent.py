from __future__ import annotations

from l2_brain.features import extract
from l2_brain.types import Action, Observation


class RecurrentController:
    """Same features plus a short hidden bearing that decays when the target is lost."""

    name = "recurrent"

    def __init__(self) -> None:
        self._bearing = 0.0
        self._side = 0.0
        self._mass = 0.0
        self._age = 1.0

    def reset(self, seed: int | None = None) -> None:
        self._bearing = 0.0
        self._side = 0.0
        self._mass = 0.0
        self._age = 1.0

    def step(self, observation: Observation) -> Action:
        feat = extract(observation)
        if feat.seen and feat.centroid is not None:
            offset = feat.centroid - 0.5
            if abs(offset) > 0.07:
                self._bearing = offset
                self._side = 1.0 if offset > 0.0 else -1.0
            self._mass = feat.mass
            self._age = 0.0
        else:
            self._bearing *= 0.96
            self._mass *= 0.96
            self._age = min(1.0, self._age + 0.04)

        if feat.seen and feat.centroid is not None:
            offset = feat.centroid - 0.5
            if feat.mass > 0.045 and abs(offset) < 0.08:
                return Action(turn=0.0, forward=0.15, engage=1.0)
            if abs(offset) < 0.06:
                return Action(turn=0.0, forward=1.0, engage=0.0)
            return Action(turn=float(max(-1.0, min(1.0, offset * 3.2))), forward=0.25, engage=0.0)

        if self._age < 0.90 and self._side != 0.0:
            return Action(turn=0.55 * self._side, forward=0.15, engage=0.0)
        return Action(turn=0.35, forward=0.0, engage=0.0)
