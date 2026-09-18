from __future__ import annotations

import numpy as np

from l2_brain.control.snn.types import LIFConfig


def update_traces(traces: np.ndarray, spikes: np.ndarray, cfg: LIFConfig) -> np.ndarray:
    """tau_r * dT/dt = -T + S(t). Forward Euler."""
    nxt = traces + (cfg.dt_ms / cfg.tau_r_ms) * (-traces + spikes)
    return np.nan_to_num(nxt, nan=0.0, posinf=1.0, neginf=0.0)


def decode_motor(traces: np.ndarray, cfg: LIFConfig, pools: tuple[slice, slice, slice, slice, slice]) -> tuple[float, float]:
    """Normalize pool traces so ~50 Hz maps forward to ~0.70 and yaw to ±0.4."""
    left_sl, right_sl, fwd_sl, _i_left, _i_right = pools
    n_e = cfg.n_e
    left = float(np.mean(traces[left_sl])) if traces[left_sl].size else 0.0
    right = float(np.mean(traces[right_sl])) if traces[right_sl].size else 0.0
    fwd = float(np.mean(traces[fwd_sl])) if traces[fwd_sl].size else 0.0
    inhib = float(np.mean(traces[n_e:])) if cfg.n_i else 0.0
    ref = max(cfg.trace_ref, 1e-9)
    level = fwd / ref
    brake = cfg.gain_inhibit_forward * (inhib / ref)
    forward = cfg.forward_ref * level - brake
    turn = cfg.turn_limit * ((right - left) / ref)
    turn = float(np.clip(turn, -cfg.turn_limit, cfg.turn_limit))
    forward = float(np.clip(forward, 0.0, 1.0))
    return turn, forward
