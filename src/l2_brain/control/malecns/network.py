"""LIF on a compact extract. Same Euler as snn_v1; W_rec is not Braitenberg."""

from __future__ import annotations

import numpy as np

from l2_brain.control.malecns.loader import (
    Subgraph,
    input_matrix,
    load_subgraph,
    role_indices,
    weight_matrix,
)
from l2_brain.control.snn.lif import integrate_step
from l2_brain.control.snn.network import _empty_state
from l2_brain.control.snn.readout import update_traces
from l2_brain.control.snn.types import LIFConfig, NetworkState, PopulationMetrics


def lif_for_graph(graph: Subgraph, *, seed: int = 0) -> LIFConfig:
    n_e = sum(1 for node in graph.nodes if node.transmitter != "gaba")
    return LIFConfig(n=graph.n, excitatory_frac=n_e / graph.n, seed=seed)


def decode_descending(
    traces: np.ndarray,
    cfg: LIFConfig,
    left: np.ndarray,
    right: np.ndarray,
    fwd: np.ndarray,
    inhib: np.ndarray,
) -> tuple[float, float]:
    ref = max(cfg.trace_ref, 1e-9)
    left_t = float(np.mean(traces[left])) if left.size else 0.0
    right_t = float(np.mean(traces[right])) if right.size else 0.0
    fwd_t = float(np.mean(traces[fwd])) if fwd.size else 0.0
    inhib_t = float(np.mean(traces[inhib])) if inhib.size else 0.0
    forward = cfg.forward_ref * (fwd_t / ref) - cfg.gain_inhibit_forward * (inhib_t / ref)
    turn = cfg.turn_limit * ((right_t - left_t) / ref)
    return (
        float(np.clip(turn, -cfg.turn_limit, cfg.turn_limit)),
        float(np.clip(forward, 0.0, 1.0)),
    )


class MaleCNSNetwork:
    """Visuo-motor extract dynamics. Not a downloaded connectome runtime."""

    def __init__(self, graph: Subgraph, config: LIFConfig | None = None) -> None:
        if config is None:
            config = lif_for_graph(graph)
        if config.n != graph.n:
            raise ValueError("LIFConfig.n must match extract size")
        self.graph = graph
        self.config = config
        self.w_rec = weight_matrix(graph)
        self.w_in = input_matrix(graph, n_input=config.n_input, scale=config.w_in_scale)
        self.dn_left = role_indices(graph, "dn_left")
        self.dn_right = role_indices(graph, "dn_right")
        self.dn_fwd = role_indices(graph, "dn_fwd")
        self.inhib = np.array(
            [node.index for node in graph.nodes if node.transmitter == "gaba"],
            dtype=np.int32,
        )
        self.state = _empty_state(config)

    @classmethod
    def from_mode(cls, mode: str = "bio", *, seed: int = 0) -> MaleCNSNetwork:
        graph = load_subgraph(mode, seed=seed)  # type: ignore[arg-type]
        return cls(graph, lif_for_graph(graph, seed=seed))

    def reset(self) -> None:
        self.state = _empty_state(self.config)

    def get_state(self) -> NetworkState:
        return self.state.copy()

    def set_state(self, state: NetworkState) -> None:
        if state.v.shape != (self.config.n,):
            raise ValueError("state size does not match extract")
        self.state = state.copy()

    def step_tick(self, sensory: np.ndarray, *, apply_tonic: bool = True) -> tuple[np.ndarray, PopulationMetrics]:
        cfg = self.config
        sense = np.asarray(sensory, dtype=np.float64).reshape(cfg.n_input)
        i_ext = self.w_in @ sense
        if apply_tonic and self.dn_fwd.size:
            i_ext[self.dn_fwd] += cfg.tonic_e
        spikes = self.state.last_spikes
        spike_counts = np.zeros(cfg.n, dtype=np.int32)
        st = self.state
        for _ in range(cfg.steps_per_tick):
            st.v, st.i_syn, st.refrac, spikes = integrate_step(
                st.v, st.i_syn, st.refrac, spikes, i_ext, self.w_rec, cfg
            )
            st.traces = update_traces(st.traces, spikes, cfg)
            spike_counts += (spikes > 0.5).astype(np.int32)
        st.last_spikes = spikes
        st.silent_hits[st.silent_cursor] = (spike_counts > 0).astype(np.int8)
        st.silent_cursor = (st.silent_cursor + 1) % cfg.silent_window_ticks
        st.tick_index += 1
        return st.traces.copy(), self._metrics(spike_counts)

    def _metrics(self, spike_counts: np.ndarray) -> PopulationMetrics:
        cfg = self.config
        tick_s = cfg.tick_ms / 1000.0
        e_mask = np.array([node.transmitter != "gaba" for node in self.graph.nodes])
        n_e = int(e_mask.sum())
        n_i = cfg.n - n_e
        total = float(spike_counts.sum())
        e_sum = float(spike_counts[e_mask].sum()) if n_e else 0.0
        i_sum = float(spike_counts[~e_mask].sum()) if n_i else 0.0
        filled = min(cfg.silent_window_ticks, max(self.state.tick_index, 1))
        window = self.state.silent_hits[:filled]
        silent = float(np.mean(window.sum(axis=0) == 0)) if filled else 1.0
        v = self.state.v
        return PopulationMetrics(
            firing_rate_hz=total / (cfg.n * tick_s),
            excitatory_rate_hz=e_sum / (max(n_e, 1) * tick_s),
            inhibitory_rate_hz=i_sum / (max(n_i, 1) * tick_s),
            silent_ratio=silent,
            saturated_ratio=float(np.mean(spike_counts == cfg.steps_per_tick)),
            v_min=float(v.min()),
            v_mean=float(v.mean()),
            v_max=float(v.max()),
            steps=cfg.steps_per_tick,
            n=cfg.n,
        )
