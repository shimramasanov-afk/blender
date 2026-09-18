from __future__ import annotations

import numpy as np

from l2_brain.features import extract
from l2_brain.types import Action, Observation


class SpikingController:
    """Tiny LIF layer. Not MaleCNS. Same visual features as the baselines."""

    name = "snn"

    def __init__(self, n_neurons: int = 6) -> None:
        self.n_neurons = n_neurons
        self._v = np.zeros(n_neurons, dtype=np.float64)
        self._decay = 0.88
        self._threshold = 1.0
        # columns: left, center, right, bias
        self._w = np.array(
            [
                [2.4, 0.1, 0.0, 0.15],
                [1.6, 0.2, 0.0, 0.10],
                [0.1, 2.2, 0.1, 0.05],
                [0.0, 1.8, 0.0, 0.05],
                [0.0, 0.1, 2.4, 0.15],
                [0.0, 0.2, 1.6, 0.10],
            ],
            dtype=np.float64,
        )

    def reset(self, seed: int | None = None) -> None:
        self._v[:] = 0.0

    def step(self, observation: Observation) -> Action:
        feat = extract(observation)
        x = np.array([feat.left, feat.center, feat.right, 0.08], dtype=np.float64)
        self._v = self._v * self._decay + self._w @ x
        spikes = self._v >= self._threshold
        self._v = self._v * (~spikes)
        left = float(spikes[0]) + 0.5 * float(spikes[1])
        center = float(spikes[2]) + 0.5 * float(spikes[3])
        right = float(spikes[4]) + 0.5 * float(spikes[5])
        turn = right - left
        if not feat.seen and left + center + right == 0:
            return Action(turn=0.35, forward=0.0, engage=0.0)
        close = (
            feat.mass > 0.045
            and feat.centroid is not None
            and abs(feat.centroid - 0.5) < 0.08
        )
        # Spikes steer; the close-gate is the same visual rule as the other controllers.
        if close:
            return Action(turn=0.0, forward=0.15, engage=1.0)
        forward = 1.0 if center > left and center > right else 0.35
        return Action(turn=float(np.clip(turn, -1.0, 1.0)), forward=forward, engage=0.0)
