from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GRUConfig:
    """One-layer GRU, forward-only. No training, no autograd."""

    n_in: int = 6
    hidden: int = 16
    with_memory: bool = True
    fov_half_rad: float = 0.6
    k_turn: float = 0.40
    k_forward: float = 0.72
    residual_scale: float = 0.0
    seed: int = 0

    def __post_init__(self) -> None:
        if self.n_in < 1 or self.hidden < 1:
            raise ValueError("n_in and hidden must be >= 1")
        if self.fov_half_rad <= 0.0:
            raise ValueError("fov_half_rad must be positive")
        if not 0.0 < self.k_turn <= 1.0 or not 0.0 < self.k_forward <= 1.0:
            raise ValueError("k_turn and k_forward must be in (0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
