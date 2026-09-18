from l2_brain.cli import main
from l2_brain.io.cgevent_backend import CGEventInputBackend, LiveInputNotConfirmed, RecordingPoster
from l2_brain.live.agent_cli import parse_agent_live_args, run_agent_live
from l2_brain.live.perception import PerceptionHub
from l2_brain.live.runtime import LiveRuntime
from l2_brain.vision.hud_parser import HUDParser

from test_hud_parser import _layout, _scene
from test_live_runtime import _Clock, _Grab


def test_cli_help_lists_agent_live() -> None:
    try:
        main(["agent-live", "--help"])
    except SystemExit as exc:
        assert exc.code == 0


def test_parse_defaults_are_observe_only() -> None:
    args = parse_agent_live_args([])
    assert args.live is False
    assert args.danger_confirmed is False
    assert args.skill is None
    assert args.task is None
    assert args.repeat == 1
    assert args.ticks == 8


def test_skill_without_flags_is_rejected() -> None:
    args = parse_agent_live_args(["--skill", "target-next"])
    lines: list[str] = []
    code = run_agent_live(args, printer=lines.append)
    assert code == 2
    assert "live_flags_required" in lines[0]


def test_observe_injected_runtime_no_backend() -> None:
    clock = _Clock()
    rt = LiveRuntime(
        PerceptionHub(
            HUDParser(_layout()),
            focus_probe=lambda: True,
            frames=_Grab(_scene(hp=1.0, mp=1.0, cp=1.0, target=False)),
            now_ns=clock,
        ),
        backend=None,
        clock=clock,
        sleeper=lambda s: None,
    )
    args = parse_agent_live_args(["--ticks", "2"])
    lines: list[str] = []
    code = run_agent_live(args, runtime=rt, printer=lines.append)
    assert code == 0
    assert "observe-only" in lines[0]
    assert '"task": null' in lines[0]
    assert rt.backend is None
    assert rt.summary()["closed"] is True


def test_cgevent_still_requires_dual_flags() -> None:
    try:
        CGEventInputBackend(1, live_confirmed=True, live_danger_confirmed=False, poster=RecordingPoster())
    except LiveInputNotConfirmed:
        return
    raise AssertionError("dual flags required")
