"""Current-based LIF, forward Euler, CPU.

    tau_m * dV/dt     = -(V - V_reset) + I_syn
    tau_s * dI_syn/dt = -I_syn + drive
    drive             = I_ext + W @ S(t)

V, I in model units. Time in milliseconds. No Metal/MPS. No STDP.
"""

from __future__ import annotations

import numpy as np

from l2_brain.control.snn.types import LIFConfig


def _finite(values: np.ndarray, *, lo: float, hi: float, fill: float) -> np.ndarray:
    clean = np.nan_to_num(values, nan=fill, posinf=hi, neginf=lo)
    return np.clip(clean, lo, hi)


def integrate_step(
    v: np.ndarray,
    i_syn: np.ndarray,
    refrac: np.ndarray,
    spikes_in: np.ndarray,
    i_ext: np.ndarray,
    w_rec: np.ndarray,
    cfg: LIFConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """One Euler step. spikes_in is S(t) from the previous step (or zeros)."""
    dt = cfg.dt_ms
    drive = i_ext + w_rec @ spikes_in.astype(np.float64, copy=False)
    drive = _finite(drive, lo=-cfg.i_max, hi=cfg.i_max, fill=0.0)
    i_syn = i_syn + (dt / cfg.tau_s_ms) * (-i_syn + drive)
    i_syn = _finite(i_syn, lo=-cfg.i_max, hi=cfg.i_max, fill=0.0)

    active = refrac <= 0
    dv = (dt / cfg.tau_m_ms) * (-(v - cfg.v_reset) + i_syn)
    v = np.where(active, v + dv, cfg.v_reset)
    v = _finite(v, lo=cfg.v_min, hi=cfg.v_th, fill=cfg.v_reset)

    spiked = active & (v >= cfg.v_th)
    v = np.where(spiked, cfg.v_reset, v)
    if cfg.refrac_steps > 0:
        refrac = np.where(spiked, cfg.refrac_steps, np.maximum(refrac - 1, 0))
        v = np.where(refrac > 0, cfg.v_reset, v)
    else:
        refrac = np.zeros_like(refrac)
    return v, i_syn, refrac, spiked.astype(np.float64, copy=False)


def integrate_current(
    v: np.ndarray,
    i_syn: np.ndarray,
    refrac: np.ndarray,
    i_ext: np.ndarray,
    cfg: LIFConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Single-population step with no recurrent matrix (unit tests)."""
    n = int(v.shape[0])
    zeros = np.zeros(n, dtype=np.float64)
    w = np.zeros((n, n), dtype=np.float64)
    return integrate_step(v, i_syn, refrac, zeros, i_ext, w, cfg)
