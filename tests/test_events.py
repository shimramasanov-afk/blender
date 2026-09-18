from __future__ import annotations

from l2_brain.control.events import PHYSICAL_BLOCK_S, STAGNATION_S, score_events, seconds_per_tick, ticks_for


def test_clock_is_documented() -> None:
    assert seconds_per_tick(20) == 0.05
    assert ticks_for(PHYSICAL_BLOCK_S, 20) == 8
    assert ticks_for(STAGNATION_S, 20) == 25


def test_events_overlap_and_are_not_exclusive() -> None:
    traces = []
    for i in range(30):
        traces.append(
            {
                "dist": 5.0,
                "x": 3.0,
                "y": 8.0,
                "cmd_forward": 0.6,
                "goal_visible": False,
                "in_fov": False,
                "dropped": False,
                "stale": False,
                "reason": "search",
                "situation": "move",
                "recovering": False,
            }
        )
    events = score_events(traces, success=False, timeout=True, tick_hz=20)
    assert events["gt"]["physical_blockage"]
    assert events["gt"]["navigation_stagnation"]
    assert events["gt"]["target_unobserved"]
    assert events["gt"]["episode_timeout"]
    assert events["controller"]["searching"]
    assert events["controller"]["privileged"] is False


def test_recall_na_when_no_positive_events() -> None:
    from l2_brain.control.events import rate_or_na

    assert rate_or_na(0, 0) is None
    assert rate_or_na(1, 2) == 0.5
