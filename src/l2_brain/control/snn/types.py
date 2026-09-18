from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class LIFConfig:
    """Fixed LIF + current synapse. Units: mV-like, ms, nA-like. No plasticity."""

    n: int = 64
    n_input: int = 6
    excitatory_frac: float = 0.80
    density: float = 0.20
    dt_ms: float = 1.0
    tick_ms: float = 50.0
    tau_m_ms: float = 20.0
    tau_s_ms: float = 5.0
    tau_r_ms: float = 10.0
    v_reset: float = 0.0
    v_th: float = 1.0
    v_min: float = -1.0
    t_ref_ms: float = 2.0
    i_max: float = 40.0
    w_scale: float = 0.35
    w_in_scale: float = 1.80
    w_inh: float = 0.85
    tonic_e: float = 1.05
    seed: int = 0
    silent_window_ticks: int = 20
    readout_rate_hz: float = 50.0
    forward_ref: float = 0.70
    turn_limit: float = 0.40
    gain_inhibit_forward: float = 0.25
    fov_half_rad: float = 0.6

    def __post_init__(self) -> None:
        if self.n < 8:
            raise ValueError("n must be >= 8")
        if not 0.0 < self.excitatory_frac < 1.0:
            raise ValueError("excitatory_frac must be in (0, 1)")
        if not 0.0 < self.density <= 1.0:
            raise ValueError("density must be in (0, 1]")
        if self.dt_ms <= 0.0 or self.tick_ms <= 0.0:
            raise ValueError("dt_ms and tick_ms must be positive")
        if self.tau_m_ms <= 0.0 or self.tau_s_ms <= 0.0 or self.tau_r_ms <= 0.0:
            raise ValueError("time constants must be positive")
        if self.v_th <= self.v_reset:
            raise ValueError("v_th must be > v_reset")
        if self.t_ref_ms < 0.0 or self.i_max <= 0.0:
            raise ValueError("t_ref_ms must be >= 0 and i_max > 0")
        if self.n_input < 1 or self.silent_window_ticks < 1:
            raise ValueError("n_input and silent_window_ticks must be >= 1")
        if self.readout_rate_hz <= 0.0 or not 0.0 < self.forward_ref <= 1.0:
            raise ValueError("readout_rate_hz must be > 0 and forward_ref in (0, 1]")
        if not 0.0 < self.turn_limit <= 1.0 or self.w_inh < 0.0:
            raise ValueError("turn_limit must be in (0, 1] and w_inh >= 0")

    @property
    def n_e(self) -> int:
        return max(1, int(round(self.n * self.excitatory_frac)))

    @property
    def n_i(self) -> int:
        return max(1, self.n - self.n_e)

    @property
    def steps_per_tick(self) -> int:
        steps = int(round(self.tick_ms / self.dt_ms))
        if steps < 1:
            raise ValueError("tick_ms / dt_ms must round to >= 1")
        return steps

    @property
    def refrac_steps(self) -> int:
        return max(0, int(round(self.t_ref_ms / self.dt_ms)))

    @property
    def trace_ref(self) -> float:
        return self.readout_rate_hz * self.dt_ms / 1000.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NetworkState:
    v: np.ndarray
    i_syn: np.ndarray
    refrac: np.ndarray
    traces: np.ndarray
    last_spikes: np.ndarray
    silent_hits: np.ndarray
    silent_cursor: int
    tick_index: int

    def copy(self) -> NetworkState:
        return NetworkState(
            v=self.v.copy(),
            i_syn=self.i_syn.copy(),
            refrac=self.refrac.copy(),
            traces=self.traces.copy(),
            last_spikes=self.last_spikes.copy(),
            silent_hits=self.silent_hits.copy(),
            silent_cursor=int(self.silent_cursor),
            tick_index=int(self.tick_index),
        )


@dataclass(frozen=True, slots=True)
class PopulationMetrics:
    firing_rate_hz: float
    excitatory_rate_hz: float
    inhibitory_rate_hz: float
    silent_ratio: float
    saturated_ratio: float
    v_min: float
    v_mean: float
    v_max: float
    steps: int
    n: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
