from l2_brain.bench.suite_runner import (
    CONTROLLERS,
    MINI_SUITE,
    accounting,
    build_controller,
    suite_specs,
)


def test_mini_suite_is_five_training_v0_scenes() -> None:
    specs = suite_specs(0)
    assert len(specs) == 5
    assert [item.episode_id for item in specs] == [
        "open_goal:training:v0:s0",
        "camera_spin:training:v0:s0",
        "latency_drops:training:v0:s0",
        "vanishing_target:training:v0:s0",
        "single_obstacle:training:v0:s0",
    ]
    assert MINI_SUITE[0][0] == "open_goal"
    assert "snn_rstdp" in CONTROLLERS
    assert "malecns_bio" in CONTROLLERS


def test_factory_and_accounting_do_not_edit_policies() -> None:
    for name in ("baseline_memory_v1", "gru_v1", "snn_v1", "malecns_bio"):
        controller = build_controller(name, seed=0)
        acc = accounting(name, controller)
        assert acc["n_params"] > 0
        assert acc["k_substeps"] >= 1
        assert acc["state_floats"] >= 1
