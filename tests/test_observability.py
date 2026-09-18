from __future__ import annotations

from l2_brain.sim.config import EpisodeSpec, SimConfig
from l2_brain.sim.observability import classify, look_around_visible
from l2_brain.sim.views import AgentView, GroundTruth


def test_open_goal_is_visible() -> None:
    spec = EpisodeSpec("open_goal", "training", 0, 0, SimConfig())
    info = look_around_visible(spec)
    assert info["start_observed"]
    assert classify(info, spec) == "visible_goal"


def test_u_trap_needs_turn_not_map() -> None:
    spec = EpisodeSpec("u_trap", "training", 0, 0, SimConfig())
    info = look_around_visible(spec)
    assert not info["start_in_fov"]
    assert info["start_los"]
    assert info["visible_after_turn_in_place"]
    assert not info["requires_exploration"]


def test_obstacle_requires_exploration() -> None:
    spec = EpisodeSpec("single_obstacle", "training", 0, 0, SimConfig())
    info = look_around_visible(spec)
    assert not info["start_los"]
    assert not info["visible_after_turn_in_place"]
    assert info["requires_exploration"]


def test_agent_view_still_has_no_xy() -> None:
    assert "agent_xy" not in AgentView.__dataclass_fields__
    assert "goal_xy" in GroundTruth.__dataclass_fields__
