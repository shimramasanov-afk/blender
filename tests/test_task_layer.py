"""Task layer v1. No real HID. RecordingPoster only."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster
from l2_brain.live.agent_cli import _repeat_count, parse_agent_live_args, run_agent_live
from l2_brain.live.runtime import LiveRuntime
from l2_brain.live.skills.registry import SkillRegistry
from l2_brain.live.skills.result import SkillResult, SkillStatus
from l2_brain.live.tasks.guide_interaction import GuideInteractionTask, GuidePhase
from l2_brain.live.tasks.result import TaskStatus
from l2_brain.live.tasks.runner import TaskRunner
from l2_brain.live.world_state import AgentMode, WorldState
from l2_brain.cli import main

from test_npc_dialog import _Clock

TASK_DIR = Path(__file__).resolve().parents[1] / "src" / "l2_brain" / "live" / "tasks"
FORBIDDEN_IMPORTS = frozenset(
    {
        "CGEventInputBackend",
        "GameAction",
        "AttackTarget",
        "LootTarget",
        "TargetNext",
        "send_live",
        "HoldKey",
        "SkillActivate",
    }
)
FORBIDDEN_TEXT = (
    "CGEventInputBackend",
    "GameAction",
    "AttackTarget",
    "LootTarget",
    "TargetNext",
    "send_live",
    "send_action",
    "roam",
    "MaleCNS",
    "ScreenCaptureKit",
    "recover_capture",
)


def _ws(*, dialog_open=False, focus_ok=True, capture_ok=True) -> WorldState:
    return WorldState(
        timestamp_ns=1,
        capture_ok=capture_ok,
        focus_ok=focus_ok,
        self_hp=1.0,
        self_cp=1.0,
        self_mp=1.0,
        target_locked=False,
        target_hp=None,
        target_dead=False,
        dialog_open=dialog_open,
        dialog_items=(),
        ui_modal_open=False,
        motion_magnitude=0.0,
        last_error=None,
        frame_width=300,
        frame_height=200,
        hud_valid=True,
    )


class _Hub:
    def __init__(self) -> None:
        self.dialog = False
        self.want_dialog = False
        self.focus_ok = True
        self.capture_ok = True

    def observe(self) -> WorldState:
        if self.want_dialog:
            self.dialog = True
        return _ws(dialog_open=self.dialog, focus_ok=self.focus_ok, capture_ok=self.capture_ok)


class _Book:
    def __init__(self, hub: _Hub) -> None:
        self.hub = hub
        self.open_starts = 0
        self.open_fails_left = 0
        self.boom_on_tick = False
        self.close_starts = 0


class _Open:
    name = "open_npc_dialog"

    def __init__(self, book: _Book, npc_name: str = "Newbie Guide", **_: object) -> None:
        self.book = book
        self.npc_name = npc_name

    def can_start(self, state: WorldState) -> bool:
        return True

    def start(self, context: object, state: WorldState) -> SkillResult:
        self.book.open_starts += 1
        if self.book.open_fails_left > 0:
            self.book.open_fails_left -= 1
            return SkillResult(SkillStatus.FAILED, reason="dialog_timeout")
        self.book.hub.want_dialog = True
        return SkillResult(SkillStatus.RUNNING, reason="opening")

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if self.book.boom_on_tick:
            raise RuntimeError("skill_boom")
        if state.dialog_open is True:
            self.book.hub.want_dialog = False
            return SkillResult(SkillStatus.SUCCESS, reason="dialog_open")
        return SkillResult(SkillStatus.RUNNING, reason="opening")

    def cancel(self, context: object, reason: str) -> SkillResult:
        return SkillResult(SkillStatus.ABORTED, reason=reason)


class _Close:
    name = "close_dialog"

    def __init__(self, book: _Book, **_: object) -> None:
        self.book = book

    def can_start(self, state: WorldState) -> bool:
        return True

    def start(self, context: object, state: WorldState) -> SkillResult:
        self.book.close_starts += 1
        self.book.hub.want_dialog = False
        self.book.hub.dialog = False
        return SkillResult(SkillStatus.RUNNING, reason="escape_sent")

    def tick(self, context: object, state: WorldState) -> SkillResult:
        if state.dialog_open is True:
            return SkillResult(SkillStatus.FAILED, reason="dialog_still_open")
        return SkillResult(SkillStatus.SUCCESS, reason="dialog_closed")

    def cancel(self, context: object, reason: str) -> SkillResult:
        return SkillResult(SkillStatus.ABORTED, reason=reason)


def _backend(clock: _Clock) -> CGEventInputBackend:
    return CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=RecordingPoster(),
        focus_probe=lambda: True,
        now_ns=clock,
    )


def _harness(*, recover_capture=None):
    clock = _Clock()
    hub = _Hub()
    book = _Book(hub)
    registry = SkillRegistry()
    registry.register("open_npc_dialog", lambda **kwargs: _Open(book, **kwargs))
    registry.register("close_dialog", lambda **kwargs: _Close(book, **kwargs))
    backend = _backend(clock)
    runtime = LiveRuntime(
        hub,
        backend=backend,
        registry=registry,
        clock=clock,
        sleeper=lambda _s: None,
        recover_capture=recover_capture,
    )
    return hub, book, backend, runtime, TaskRunner(runtime)


def _drive_success(runner: TaskRunner) -> None:
    started = runner.start(GuideInteractionTask("Newbie Guide"))
    assert started.status is TaskStatus.RUNNING
    assert started.data.get("phase") == GuidePhase.TARGET_AND_OPEN.value
    mid = runner.tick()
    assert mid.status is TaskStatus.RUNNING
    assert runner.runtime.active_skill is not None
    assert runner.runtime.active_skill.name == "close_dialog"
    done = runner.tick()
    assert done.status is TaskStatus.SUCCESS
    assert done.reason == "guide_open_close_done"


def test_guide_success_open_then_close_returns_idle() -> None:
    _hub, book, backend, runtime, runner = _harness()
    assert runtime.mode is AgentMode.IDLE
    _drive_success(runner)
    assert runtime.mode is AgentMode.IDLE
    assert runtime.active_skill is None
    assert book.open_starts == 1
    assert book.close_starts == 1
    trace = runner.task.trace
    skills = [row.get("skill") for row in trace if "skill" in row]
    assert "open_npc_dialog" in skills
    assert "close_dialog" in skills
    states = [row.get("state") for row in trace]
    assert "target_and_open" in states
    assert "verify_open" in states
    assert "close" in states
    assert "success" in states
    assert any(row.get("result") == "SUCCESS" and row.get("state") == "verify_open" for row in trace)
    assert not any(row.reason == "release_all" and row.hid_sent for row in backend.log)


def test_open_timeout_one_recovery_then_success() -> None:
    _hub, book, _backend, runtime, runner = _harness()
    book.open_fails_left = 1
    started = runner.start(GuideInteractionTask())
    assert started.status is TaskStatus.RUNNING
    assert book.open_starts == 1
    assert book.close_starts == 1
    after_escape = runner.tick()
    assert after_escape.status is TaskStatus.RUNNING
    assert book.open_starts == 2
    done = runner.tick()
    assert done.status is TaskStatus.RUNNING
    done = runner.tick()
    assert done.status is TaskStatus.SUCCESS
    assert any(row.get("result") == "RETRY" for row in runner.task.trace)
    assert runtime.mode is AgentMode.IDLE


def test_retry_exhausted_fails() -> None:
    _hub, book, _backend, _runtime, runner = _harness()
    book.open_fails_left = 2
    started = runner.start(GuideInteractionTask())
    assert started.status is TaskStatus.RUNNING
    failed = runner.tick()
    assert failed.status is TaskStatus.FAILED
    assert failed.reason == "retry_exhausted"
    assert book.open_starts == 2


def test_focus_lost_aborts_and_releases() -> None:
    hub, _book, backend, runtime, runner = _harness()
    started = runner.start(GuideInteractionTask())
    assert started.status is TaskStatus.RUNNING
    hub.focus_ok = False
    done = runner.tick()
    assert done.status is TaskStatus.ABORTED
    assert done.reason == "focus_lost"
    assert runtime.mode is AgentMode.ABORTED
    assert any(row.reason == "release_all" for row in backend.log)


def test_capture_lost_without_recovery_aborts() -> None:
    hub, _book, backend, runtime, runner = _harness()
    started = runner.start(GuideInteractionTask())
    assert started.status is TaskStatus.RUNNING
    hub.capture_ok = False
    done = runner.tick()
    assert done.status is TaskStatus.ABORTED
    assert done.reason == "capture_lost"
    assert runtime.mode is AgentMode.ABORTED
    assert any(row.reason == "release_all" for row in backend.log)


def test_f12_aborts() -> None:
    _hub, _book, backend, runtime, runner = _harness()
    started = runner.start(GuideInteractionTask())
    assert started.status is TaskStatus.RUNNING
    backend.poll_kill_switch = lambda: True  # type: ignore[method-assign]
    done = runner.tick()
    assert done.status is TaskStatus.ABORTED
    assert done.reason == "kill_switch"
    assert any(row.reason == "release_all" for row in backend.log)


def test_skill_exception_aborts_and_releases() -> None:
    _hub, book, backend, runtime, runner = _harness()
    started = runner.start(GuideInteractionTask())
    assert started.status is TaskStatus.RUNNING
    book.boom_on_tick = True
    done = runner.tick()
    assert done.status is TaskStatus.ABORTED
    assert done.reason == "exception"
    assert any(row.reason == "release_all" for row in backend.log)
    assert runtime.mode is AgentMode.ABORTED


def test_task_modules_do_not_reach_hid_or_combat() -> None:
    for path in sorted(TASK_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[-1])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.update(node.module.split("."))
                for alias in node.names:
                    imported.add(alias.name)
        assert imported.isdisjoint(FORBIDDEN_IMPORTS), (path.name, imported & FORBIDDEN_IMPORTS)
        if path.name == "__init__.py":
            continue
        for token in FORBIDDEN_TEXT:
            assert token not in source, f"{path.name} mentions {token}"
    guide_src = (TASK_DIR / "guide_interaction.py").read_text(encoding="utf-8")
    assert "start_skill" in inspect.getsource(GuideInteractionTask)
    assert 'OPEN_SKILL = "open_npc_dialog"' in guide_src
    assert 'CLOSE_SKILL = "close_dialog"' in guide_src
    assert "AttackTarget" not in guide_src
    assert "CGEvent" not in inspect.getsource(TaskRunner)


def test_task_cli_defaults_and_flags() -> None:
    args = parse_agent_live_args([])
    assert args.task is None
    assert args.skill is None
    assert args.repeat == 1
    assert args.ticks == 8
    assert _repeat_count(parse_agent_live_args(["--repeat", "99"])) == 10
    rejected = parse_agent_live_args(["--task", "guide-open-close"])
    lines: list[str] = []
    code = run_agent_live(rejected, printer=lines.append)
    assert code == 2
    assert "live_flags_required" in lines[0]


def test_task_cli_repeat_two_separate_tasks() -> None:
    _hub, book, _backend, runtime, _runner = _harness()
    args = parse_agent_live_args(
        [
            "--task",
            "guide-open-close",
            "--repeat",
            "2",
            "--live",
            "--danger-confirmed",
            "--ticks",
            "12",
        ]
    )
    lines: list[str] = []
    code = run_agent_live(args, runtime=runtime, printer=lines.append)
    assert code == 0
    assert "\"mode\": \"task\"" in lines[0] or '"mode": "task"' in lines[0]
    finish = lines[-1]
    assert '"task_status": "success"' in finish
    assert book.open_starts == 2
    assert '"repeat": 2' in finish


def test_legacy_cli_parsers_still_exist() -> None:
    for cmd in ("s4-npc-dialog", "s4-integrated-spot", "agent-live"):
        try:
            main([cmd, "--help"])
        except SystemExit as exc:
            assert exc.code == 0
