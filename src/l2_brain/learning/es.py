"""Black-box ES / REINFORCE without autograd. Same reward events as R-STDP."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class ESConfig:
    sigma: float = 0.03
    eta: float = 0.02
    clip: float = 0.40
    seed: int = 0


class GaussianES:
    """params ← params + η R ε, ε ~ N(0, σ). Frozen when eta=0 or freeze()."""

    def __init__(self, dim: int, config: ESConfig | None = None) -> None:
        if dim < 1:
            raise ValueError("dim must be >= 1")
        self.config = config or ESConfig()
        self.dim = dim
        self._rng = np.random.default_rng(self.config.seed)
        self.frozen = True

    def freeze(self) -> None:
        self.frozen = True

    def unfreeze(self) -> None:
        self.frozen = False

    def ask(self) -> np.ndarray:
        return self._rng.normal(0.0, self.config.sigma, self.dim)

    def tell(self, params: np.ndarray, noise: np.ndarray, reward: float) -> np.ndarray:
        vec = np.asarray(params, dtype=np.float64).reshape(self.dim)
        if self.frozen or reward == 0.0:
            return vec
        updated = vec + self.config.eta * float(reward) * np.asarray(noise, dtype=np.float64)
        return np.clip(updated, -self.config.clip, self.config.clip)
