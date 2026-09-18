from __future__ import annotations

from l2_brain.sim.config import FROZEN_SCENARIO_IDS, catalog
from l2_brain.sim.diagnostic import goal_not_inside_wall, reverse_supported, scripted_push_blockage, start_pose_legal
from l2_brain.sim.config import EpisodeSpec, SimConfig
from l2_brain.sim.observability import look_around_visible


def test_frozen_catalog_still_60() -> None:
    assert len(catalog(0, suite="frozen")) == 60
    assert catalog(0, suite="frozen")[0].scenario in FROZEN_SCENARIO_IDS


def test_aliases_match_old_traps() -> None:
    old = look_around_visible(EpisodeSpec("u_trap", "training", 0, 0, SimConfig()))
    new = look_around_visible(EpisodeSpec("rear_goal_u", "training", 0, 0, SimConfig()))
    assert old["start_in_fov"] == new["start_in_fov"]
    assert old["visible_after_turn_in_place"] == new["visible_after_turn_in_place"]


def test_new_starts_and_goals_are_legal() -> None:
    for name in ("detour_visible", "side_hold_jog", "loop_yard", "push_wall"):
        spec = EpisodeSpec(name, "training", 0, 0, SimConfig())
        assert start_pose_legal(spec)
        assert goal_not_inside_wall(spec)


def test_scripted_wall_creates_physical_blockage() -> None:
    result = scripted_push_blockage(ticks=16)
    assert result["not_autonomous_eval"]
    assert result["physical_blockage"]
    assert result["windows"] >= 1


def test_reverse_not_in_contract() -> None:
    assert reverse_supported() is False


def test_detour_is_visible_but_not_straight() -> None:
    spec = EpisodeSpec("detour_visible", "training", 0, 0, SimConfig())
    info = look_around_visible(spec)
    assert info["start_observed"] or info["visible_after_turn_in_place"]
