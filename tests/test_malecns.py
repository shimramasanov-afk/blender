from __future__ import annotations

import numpy as np

from l2_brain.control.malecns.compare import EPISODE_ID, run_malecns_compare
from l2_brain.control.malecns.loader import (
    TRANSMITTER_SIGN,
    load_subgraph,
    out_degrees,
    transmitter_sign,
    weight_matrix,
)
from l2_brain.control.malecns.network import MaleCNSNetwork


def test_extract_size_and_metadata() -> None:
    graph = load_subgraph("bio")
    assert graph.source == "synthetic_extract"
    assert graph.biological_claim is False
    assert graph.metadata()["full_connectome_loaded"] is False
    assert 150 <= graph.n <= 250
    assert graph.e > 0
    assert 0.0 < graph.density < 1.0


def test_dale_signs_follow_transmitters() -> None:
    graph = load_subgraph("bio")
    by_index = {node.index: node for node in graph.nodes}
    for edge in graph.edges:
        pre = by_index[edge.pre]
        assert edge.transmitter == pre.transmitter
        assert transmitter_sign(edge.transmitter) == TRANSMITTER_SIGN[pre.transmitter]
    weights = weight_matrix(graph)
    for node in graph.nodes:
        column = weights[:, node.index]
        if node.transmitter == "gaba":
            assert np.all(column <= 0.0)
        else:
            assert np.all(column >= 0.0)


def test_bio_has_vis_to_dn_path_and_no_isolates() -> None:
    graph = load_subgraph("bio")
    from l2_brain.control.malecns.loader import has_input_to_output_path

    assert has_input_to_output_path(graph)
    degree = np.zeros(graph.n, dtype=np.int32)
    for edge in graph.edges:
        degree[edge.pre] += 1
        degree[edge.post] += 1
    assert int(degree.min()) > 0


def test_shuffle_preserves_out_degree() -> None:
    bio = load_subgraph("bio")
    shuffled = load_subgraph("shuffled", seed=0)
    assert np.array_equal(out_degrees(bio), out_degrees(shuffled))


def test_random_sparse_keeps_density_order() -> None:
    bio = load_subgraph("bio")
    rnd = load_subgraph("random_sparse", seed=0)
    assert rnd.n == bio.n
    assert abs(rnd.density - bio.density) / bio.density < 0.35


def test_dynamics_finite_and_decay_without_stimulus() -> None:
    net = MaleCNSNetwork.from_mode("bio", seed=0)
    zeros = np.zeros(net.config.n_input, dtype=np.float64)
    traces, metrics = net.step_tick(zeros, apply_tonic=False)
    assert np.isfinite(traces).all()
    assert np.isfinite(metrics.v_min)
    late_rate = []
    for _ in range(12):
        traces, metrics = net.step_tick(zeros, apply_tonic=False)
        late_rate.append(metrics.firing_rate_hz)
        assert np.isfinite(net.state.v).all()
        assert np.isfinite(net.state.i_syn).all()
        assert not np.isnan(traces).any()
    assert late_rate[-1] <= late_rate[0] + 1e-9
    assert float(np.max(np.abs(net.state.i_syn))) < 0.05


def test_huge_drive_stays_finite() -> None:
    net = MaleCNSNetwork.from_mode("bio", seed=0)
    huge = np.full(net.config.n_input, 1.0e3, dtype=np.float64)
    for _ in range(4):
        traces, metrics = net.step_tick(huge)
        assert np.isfinite(traces).all()
        assert np.isfinite(metrics.v_max)
        assert metrics.v_max <= net.config.v_th + 1e-12


def test_open_goal_compare_completes() -> None:
    rows = run_malecns_compare(seed=0)
    names = [row.controller for row in rows]
    assert names == ["snn_v1", "malecns_bio", "malecns_shuffled", "malecns_random"]
    assert all(row.episode_id == EPISODE_ID for row in rows)
    assert all(row.outcome in {"success", "timeout", "stuck", "oscillate"} for row in rows)
    assert all(row.ticks >= 1 for row in rows)
    snn = next(row for row in rows if row.controller == "snn_v1")
    assert snn.ticks == 61
    assert snn.success
