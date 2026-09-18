from __future__ import annotations

import numpy as np

from l2_brain.control.snn.lif import integrate_step
from l2_brain.control.snn.readout import update_traces
from l2_brain.control.snn.types import LIFConfig, NetworkState, PopulationMetrics

# E: left | right | forward. I: anti-left | anti-right (contralateral brake).
PoolSlices = tuple[slice, slice, slice, slice, slice]


def motor_pools(cfg: LIFConfig) -> PoolSlices:
    n_e, n_i, n = cfg.n_e, cfg.n_i, cfg.n
    third = max(1, n_e // 3)
    left = slice(0, third)
    right = slice(third, min(n_e, 2 * third))
    fwd = slice(min(n_e, 2 * third), n_e)
    mid_i = n_e + max(1, n_i // 2)
    i_left = slice(n_e, min(n, mid_i))
    i_right = slice(min(n, mid_i), n)
    return left, right, fwd, i_left, i_right


def _empty_state(cfg: LIFConfig) -> NetworkState:
    n = cfg.n
    return NetworkState(
        v=np.full(n, cfg.v_reset, dtype=np.float64),
        i_syn=np.zeros(n, dtype=np.float64),
        refrac=np.zeros(n, dtype=np.int32),
        traces=np.zeros(n, dtype=np.float64),
        last_spikes=np.zeros(n, dtype=np.float64),
        silent_hits=np.zeros((cfg.silent_window_ticks, n), dtype=np.int8),
        silent_cursor=0,
        tick_index=0,
    )


def build_recurrent(cfg: LIFConfig) -> np.ndarray:
    """Dale: E columns >= 0, I columns <= 0. I is contralateral, not random."""
    left, right, fwd, i_left, i_right = motor_pools(cfg)
    n = cfg.n
    weights = np.zeros((n, n), dtype=np.float64)
    if i_left.start < i_left.stop:
        weights[left, i_left] = -cfg.w_inh
    if i_right.start < i_right.stop:
        weights[right, i_right] = -cfg.w_inh
    rng = np.random.default_rng(cfg.seed)
    scale = 0.25 * cfg.w_scale
    for sl in (left, right, fwd):
        idx = np.arange(n)[sl]
        if idx.size < 2:
            continue
        for pre in idx:
            for post in idx:
                if post == pre or rng.random() >= cfg.density:
                    continue
                weights[post, pre] = abs(float(rng.normal(0.0, scale)))
    np.fill_diagonal(weights, 0.0)
    return weights


def build_input(cfg: LIFConfig) -> np.ndarray:
    """Braitenberg, deterministic. Columns: left, right, conf, risk, mass, align."""
    left, right, fwd, i_left, i_right = motor_pools(cfg)
    w = np.zeros((cfg.n, cfg.n_input), dtype=np.float64)
    scale = cfg.w_in_scale
    w[left, 0] = scale
    w[right, 1] = scale
    if i_right.start < i_right.stop:
        w[i_right, 0] = scale
    if i_left.start < i_left.stop:
        w[i_left, 1] = scale
    w[fwd, 2] = scale
    w[fwd, 5] = 0.65 * scale
    w[cfg.n_e :, 3] = 0.90 * scale
    w[fwd, 4] = 0.20 * scale
    return w


class SpikingNetwork:
    """Compact E/I recurrent pool. Plasticity is optional and off by default."""

    def __init__(self, config: LIFConfig | None = None) -> None:
        self.config = config or LIFConfig()
        if self.config.n_e + self.config.n_i != self.config.n:
            raise ValueError("excitatory/inhibitory split must cover n")
        self.pools = motor_pools(self.config)
        self.w_rec = build_recurrent(self.config)
        self.w_in = build_input(self.config)
        self.state = _empty_state(self.config)

    def reset(self) -> None:
        self.state = _empty_state(self.config)

    def get_state(self) -> NetworkState:
        return self.state.copy()

    def set_state(self, state: NetworkState) -> None:
        need = self.config.n
        if state.v.shape != (need,) or state.i_syn.shape != (need,):
            raise ValueError("state size does not match network")
        self.state = state.copy()

    def step_tick(
        self,
        sensory: np.ndarray,
        plasticity: object | None = None,
    ) -> tuple[np.ndarray, PopulationMetrics]:
        """Exactly K Euler steps. No catch-up beyond steps_per_tick."""
        cfg = self.config
        sense = np.asarray(sensory, dtype=np.float64).reshape(cfg.n_input)
        i_ext = self.w_in @ sense
        _left, _right, fwd, _il, _ir = self.pools
        i_ext[fwd] += cfg.tonic_e
        spikes = self.state.last_spikes
        spike_counts = np.zeros(cfg.n, dtype=np.int32)
        st = self.state
        observe = getattr(plasticity, "observe", None) if plasticity is not None else None
        pre = np.clip(sense, 0.0, None)
        for _ in range(cfg.steps_per_tick):
            st.v, st.i_syn, st.refrac, spikes = integrate_step(
                st.v, st.i_syn, st.refrac, spikes, i_ext, self.w_rec, cfg
            )
            st.traces = update_traces(st.traces, spikes, cfg)
            spike_counts += (spikes > 0.5).astype(np.int32)
            if observe is not None:
                observe(pre, spikes, cfg.dt_ms)
        st.last_spikes = spikes
        st.silent_hits[st.silent_cursor] = (spike_counts > 0).astype(np.int8)
        st.silent_cursor = (st.silent_cursor + 1) % cfg.silent_window_ticks
        st.tick_index += 1
        metrics = self._metrics(spike_counts)
        return st.traces.copy(), metrics

    def _metrics(self, spike_counts: np.ndarray) -> PopulationMetrics:
        cfg = self.config
        tick_s = cfg.tick_ms / 1000.0
        n_e = cfg.n_e
        total = float(spike_counts.sum())
        e_sum = float(spike_counts[:n_e].sum())
        i_sum = float(spike_counts[n_e:].sum())
        filled = min(cfg.silent_window_ticks, max(self.state.tick_index, 1))
        window = self.state.silent_hits[:filled]
        silent = float(np.mean(window.sum(axis=0) == 0)) if filled else 1.0
        sat = float(np.mean(spike_counts == cfg.steps_per_tick))
        v = self.state.v
        return PopulationMetrics(
            firing_rate_hz=total / (cfg.n * tick_s),
            excitatory_rate_hz=e_sum / (n_e * tick_s),
            inhibitory_rate_hz=i_sum / (max(cfg.n_i, 1) * tick_s),
            silent_ratio=silent,
            saturated_ratio=sat,
            v_min=float(v.min()),
            v_mean=float(v.mean()),
            v_max=float(v.max()),
            steps=cfg.steps_per_tick,
            n=cfg.n,
        )
