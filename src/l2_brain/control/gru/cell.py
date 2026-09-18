"""Minimal GRU cell. Cho / PyTorch convention. Units: dimensionless. CPU NumPy."""

from __future__ import annotations

import numpy as np

from l2_brain.control.gru.types import GRUConfig


def _sig(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


class GRUCell:
    def __init__(self, config: GRUConfig) -> None:
        self.config = config
        rng = np.random.default_rng(config.seed)
        h, n_in = config.hidden, config.n_in
        scale = 0.20 / np.sqrt(n_in)
        rec = 0.15 / np.sqrt(h)
        self.W_ir = rng.normal(0.0, scale, (h, n_in))
        self.W_iz = rng.normal(0.0, scale, (h, n_in))
        self.W_in = rng.normal(0.0, scale, (h, n_in))
        self.W_hr = rng.normal(0.0, rec, (h, h))
        self.W_hz = rng.normal(0.0, rec, (h, h))
        self.W_hn = rng.normal(0.0, rec, (h, h))
        self.b_ir = np.zeros(h, dtype=np.float64)
        self.b_iz = np.zeros(h, dtype=np.float64)
        self.b_in = np.zeros(h, dtype=np.float64)
        self.b_hr = np.zeros(h, dtype=np.float64)
        self.b_hz = np.zeros(h, dtype=np.float64)
        self.b_hn = np.zeros(h, dtype=np.float64)
        # Default residual_scale=0: untrained head does not scramble the reflex.
        if config.residual_scale > 0.0:
            self.W_out = rng.normal(0.0, config.residual_scale / np.sqrt(h), (2, h))
        else:
            self.W_out = np.zeros((2, h), dtype=np.float64)
        self.b_out = np.zeros(2, dtype=np.float64)

    def step(self, x: np.ndarray, hidden: np.ndarray) -> np.ndarray:
        x = np.nan_to_num(np.asarray(x, dtype=np.float64), nan=0.0, posinf=10.0, neginf=-10.0)
        hidden = np.nan_to_num(hidden, nan=0.0, posinf=1.0, neginf=-1.0)
        reset = _sig(self.W_ir @ x + self.b_ir + self.W_hr @ hidden + self.b_hr)
        update = _sig(self.W_iz @ x + self.b_iz + self.W_hz @ hidden + self.b_hz)
        candidate = np.tanh(self.W_in @ x + self.b_in + reset * (self.W_hn @ hidden + self.b_hn))
        nxt = (1.0 - update) * candidate + update * hidden
        return np.nan_to_num(nxt, nan=0.0, posinf=1.0, neginf=-1.0)

    def readout(self, hidden: np.ndarray) -> np.ndarray:
        raw = self.W_out @ hidden + self.b_out
        return np.nan_to_num(raw, nan=0.0, posinf=1.0, neginf=-1.0)

    def parameter_arrays(self) -> tuple[np.ndarray, ...]:
        return (
            self.W_ir,
            self.W_iz,
            self.W_in,
            self.W_hr,
            self.W_hz,
            self.W_hn,
            self.b_ir,
            self.b_iz,
            self.b_in,
            self.b_hr,
            self.b_hz,
            self.b_hn,
            self.W_out,
            self.b_out,
        )

    def n_params(self) -> int:
        return int(sum(arr.size for arr in self.parameter_arrays()))
