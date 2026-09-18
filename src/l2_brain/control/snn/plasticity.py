"""Reward-modulated STDP. Separate from LIF, encoding, and readout.

    tau_e * de/dt = -e + S_pre * S_post
    ΔW_ij         = η * R * e_ij

W is clipped to keep Dale sign. Units: eligibility dimensionless, time in ms.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np


@dataclass(frozen=True, slots=True)
class PlasticityConfig:
    tau_e_ms: float = 150.0
    eta: float = 2.0e-4
    delta_max: float = 0.03
    w_max: float = 3.60
    w_min: float = 0.0
    mode: Literal["input", "recurrent"] = "input"
    n_e: int | None = None

    def __post_init__(self) -> None:
        if self.tau_e_ms <= 0.0 or self.eta < 0.0:
            raise ValueError("tau_e_ms must be > 0 and eta >= 0")
        if self.delta_max <= 0.0 or self.w_max <= self.w_min:
            raise ValueError("delta_max must be > 0 and w_max > w_min")


class RewardModulatedSTDP:
    """Three-factor rule on one weight matrix. Off until unfreeze()."""

    def __init__(self, rows: int, cols: int, config: PlasticityConfig | None = None) -> None:
        self.config = config or PlasticityConfig()
        self.eligibility = np.zeros((rows, cols), dtype=np.float64)
        self.frozen = True
        self.last_delta = 0.0
        self.last_reward = 0.0

    def reset_traces(self) -> None:
        self.eligibility.fill(0.0)
        self.last_delta = 0.0
        self.last_reward = 0.0

    def freeze(self) -> None:
        self.frozen = True

    def unfreeze(self) -> None:
        self.frozen = False

    def freeze_learning(self) -> None:
        self.freeze()

    def observe(self, pre: np.ndarray, post: np.ndarray, dt_ms: float) -> None:
        if self.frozen:
            return
        pre = np.nan_to_num(np.asarray(pre, dtype=np.float64), nan=0.0, posinf=1.0, neginf=0.0)
        post = np.nan_to_num(np.asarray(post, dtype=np.float64), nan=0.0, posinf=1.0, neginf=0.0)
        decay = float(np.exp(-dt_ms / self.config.tau_e_ms))
        coincidence = np.outer(post, pre)
        self.eligibility = decay * self.eligibility + coincidence
        np.nan_to_num(self.eligibility, copy=False, nan=0.0, posinf=10.0, neginf=-10.0)

    def decay_only(self, dt_ms: float, steps: int = 1) -> None:
        if self.frozen:
            return
        decay = float(np.exp(-dt_ms / self.config.tau_e_ms)) ** steps
        self.eligibility *= decay

    def modulate(self, weights: np.ndarray, reward: float) -> np.ndarray:
        w = np.asarray(weights, dtype=np.float64)
        if w.shape != self.eligibility.shape:
            raise ValueError("weight shape does not match eligibility")
        self.last_reward = float(reward)
        if self.frozen or reward == 0.0:
            self.last_delta = 0.0
            return w
        raw = self.config.eta * float(reward) * self.eligibility
        delta = np.clip(raw, -self.config.delta_max, self.config.delta_max)
        updated = apply_dale(w + delta, self.config)
        self.last_delta = float(np.max(np.abs(updated - w)))
        return updated

    def checkpoint(self, weights: np.ndarray) -> dict[str, Any]:
        return {
            "weights": np.asarray(weights, dtype=np.float64).copy(),
            "eligibility": self.eligibility.copy(),
            "frozen": self.frozen,
            "config": asdict(self.config),
        }

    def restore(self, payload: dict[str, Any]) -> np.ndarray:
        self.eligibility = np.asarray(payload["eligibility"], dtype=np.float64).copy()
        self.frozen = bool(payload["frozen"])
        return np.asarray(payload["weights"], dtype=np.float64).copy()


def apply_dale(weights: np.ndarray, config: PlasticityConfig) -> np.ndarray:
    """Keep Dale sign. Input mode: all W >= 0. Recurrent: E columns >= 0, I columns <= 0."""
    w = np.nan_to_num(np.asarray(weights, dtype=np.float64), nan=0.0)
    if config.mode == "input":
        return np.clip(w, max(0.0, config.w_min), config.w_max)
    n_e = config.n_e
    if n_e is None:
        raise ValueError("recurrent Dale needs n_e")
    out = w.copy()
    if n_e > 0:
        out[:, :n_e] = np.clip(out[:, :n_e], 0.0, config.w_max)
    if n_e < out.shape[1]:
        out[:, n_e:] = np.clip(out[:, n_e:], -config.w_max, 0.0)
    np.fill_diagonal(out, 0.0)
    return out
