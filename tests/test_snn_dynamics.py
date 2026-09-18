from __future__ import annotations

import math

import numpy as np

from l2_brain.control.snn.lif import integrate_current
from l2_brain.control.snn.network import SpikingNetwork, build_input, motor_pools
from l2_brain.control.snn.readout import decode_motor
from l2_brain.control.snn.types import LIFConfig


def _cfg(**kwargs: object) -> LIFConfig:
    defaults: dict[str, object] = {"n": 8, "seed": 1, "density": 0.25}
    defaults.update(kwargs)
    return LIFConfig(**defaults)  # type: ignore[arg-type]


def test_membrane_relaxes_to_reset_without_drive() -> None:
    cfg = _cfg()
    n = cfg.n
    v = np.full(n, 0.85, dtype=np.float64)
    i_syn = np.zeros(n, dtype=np.float64)
    refrac = np.zeros(n, dtype=np.int32)
    i_ext = np.zeros(n, dtype=np.float64)
    late_spikes = 0
    for step in range(250):
        v, i_syn, refrac, spikes = integrate_current(v, i_syn, refrac, i_ext, cfg)
        if step >= 200:
            late_spikes += int(spikes.sum())
    assert late_spikes == 0
    assert np.max(np.abs(v - cfg.v_reset)) < 1e-3
    assert np.max(np.abs(i_syn)) < 1e-3


def test_step_current_spikes_regularly_and_respects_refractory() -> None:
    cfg = _cfg(t_ref_ms=4.0)
    n = cfg.n
    v = np.full(n, cfg.v_reset, dtype=np.float64)
    i_syn = np.zeros(n, dtype=np.float64)
    refrac = np.zeros(n, dtype=np.int32)
    i_ext = np.full(n, 3.0, dtype=np.float64)
    times: list[int] = []
    for step in range(80):
        v, i_syn, refrac, spikes = integrate_current(v, i_syn, refrac, i_ext, cfg)
        if spikes[0] > 0.5:
            times.append(step)
    assert len(times) >= 3
    gaps = np.diff(times)
    assert np.all(gaps >= cfg.refrac_steps)
    assert math.isclose(float(np.max(gaps) - np.min(gaps)), 0.0, abs_tol=1.0)
    max_hz = 1000.0 / max(cfg.t_ref_ms, cfg.dt_ms)
    rate = len(times) / (80 * cfg.dt_ms / 1000.0)
    assert rate <= max_hz + 1e-6


def test_huge_current_stays_finite_and_bounded() -> None:
    cfg = _cfg()
    n = cfg.n
    v = np.full(n, cfg.v_reset, dtype=np.float64)
    i_syn = np.zeros(n, dtype=np.float64)
    refrac = np.zeros(n, dtype=np.int32)
    i_ext = np.full(n, 1.0e4, dtype=np.float64)
    for _ in range(40):
        v, i_syn, refrac, spikes = integrate_current(v, i_syn, refrac, i_ext, cfg)
        assert np.isfinite(v).all()
        assert np.isfinite(i_syn).all()
        assert np.isfinite(spikes).all()
        assert v.max() <= cfg.v_th + 1e-12
        assert v.min() >= cfg.v_min - 1e-12
        assert np.abs(i_syn).max() <= cfg.i_max + 1e-12


def test_get_set_state_is_bitwise_identical() -> None:
    net = SpikingNetwork(LIFConfig(n=32, seed=3, density=0.2))
    drive = np.array([0.4, 0.1, 0.6, 0.0, 0.05, 0.5], dtype=np.float64)
    net.step_tick(drive)
    snapshot = net.get_state()
    w_before = net.w_rec.copy()
    traces_a, metrics_a = net.step_tick(drive)
    after_a = net.get_state()
    net.set_state(snapshot)
    traces_b, metrics_b = net.step_tick(drive)
    after_b = net.get_state()
    assert np.array_equal(traces_a, traces_b)
    assert np.array_equal(after_a.v, after_b.v)
    assert np.array_equal(after_a.i_syn, after_b.i_syn)
    assert np.array_equal(after_a.refrac, after_b.refrac)
    assert np.array_equal(after_a.traces, after_b.traces)
    assert np.array_equal(after_a.last_spikes, after_b.last_spikes)
    assert after_a.silent_cursor == after_b.silent_cursor
    assert metrics_a == metrics_b
    assert np.array_equal(w_before, net.w_rec)


def test_dale_sign_and_no_self_synapses() -> None:
    cfg = LIFConfig(n=32, seed=2, density=0.3)
    net = SpikingNetwork(cfg)
    n_e = cfg.n_e
    assert np.all(net.w_rec[:, :n_e] >= 0.0)
    assert np.all(net.w_rec[:, n_e:] <= 0.0)
    assert np.all(np.diag(net.w_rec) == 0.0)


def test_steps_per_tick_is_exactly_k() -> None:
    cfg = LIFConfig()
    assert cfg.dt_ms == 1.0
    assert cfg.tick_ms == 50.0
    assert cfg.steps_per_tick == 50


def test_braitenberg_conf_hits_forward_pool_only() -> None:
    cfg = LIFConfig(n=32)
    weights = build_input(cfg)
    left, right, fwd, _i_left, _i_right = motor_pools(cfg)
    assert weights[fwd, 2].min() > 0.0
    assert float(weights[left, 2].max()) == 0.0
    assert float(weights[right, 2].max()) == 0.0


def test_braitenberg_bearing_excites_ipsi_and_inhibits_contra() -> None:
    cfg = LIFConfig(n=32)
    weights = build_input(cfg)
    left, right, _fwd, i_left, i_right = motor_pools(cfg)
    assert weights[left, 0].min() > 0.0
    assert float(weights[right, 0].max()) == 0.0
    assert weights[i_right, 0].min() > 0.0
    assert weights[right, 1].min() > 0.0
    assert weights[i_left, 1].min() > 0.0


def test_readout_maps_target_rate_to_cruise_band() -> None:
    cfg = LIFConfig()
    traces = np.zeros(cfg.n, dtype=np.float64)
    left, right, fwd, _il, _ir = motor_pools(cfg)
    traces[fwd] = cfg.trace_ref
    turn, forward = decode_motor(traces, cfg, (left, right, fwd, _il, _ir))
    assert 0.6 <= forward <= 0.8
    assert abs(turn) <= 0.05
    traces[left] = cfg.trace_ref
    traces[right] = 0.0
    turn_left, _fwd = decode_motor(traces, cfg, (left, right, fwd, _il, _ir))
    assert turn_left < 0.0
    assert abs(turn_left) <= cfg.turn_limit + 1e-9
