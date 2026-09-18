"""CLI for LiveRuntime. Observe-only by default. No quest/farm loop."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from l2_brain.live.runtime import LiveRuntime
from l2_brain.live.tasks.guide_interaction import GuideInteractionTask
from l2_brain.live.tasks.result import TaskStatus
from l2_brain.live.tasks.runner import TaskRunner
from l2_brain.live.world_state import AgentMode

SKILL_ALIASES: dict[str, tuple[str, dict[str, object]]] = {
    "target-next": ("target_next", {}),
    "open-guide": ("open_npc_dialog", {"npc_name": "Newbie Guide"}),
    "walk-pulse": ("walk_pulse", {}),
    "close-dialog": ("close_dialog", {}),
}

TASK_CHOICES = ("guide-open-close",)
MAX_TASK_REPEAT = 10
DEFAULT_TASK_TICK_BUDGET = 80


def add_agent_live_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--danger-confirmed", action="store_true")
    parser.add_argument("--window-id", type=int, default=None)
    parser.add_argument("--target-pid", type=int, default=None)
    parser.add_argument("--profile", type=Path, default=Path("config/window_profiles/parallels_l2.json"))
    parser.add_argument("--ticks", type=int, default=8, help="сколько observe/tick циклов")
    parser.add_argument("--skill", choices=sorted(SKILL_ALIASES), default=None)
    parser.add_argument("--task", choices=TASK_CHOICES, default=None)
    parser.add_argument("--repeat", type=int, default=1, help="сколько раз выполнить Task, cap 10")
    parser.add_argument("--npc-name", default="Newbie Guide")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="l2-brain agent-live",
        description="Единый LiveRuntime. По умолчанию observe-only, без HID.",
    )
    add_agent_live_arguments(parser)
    return parser


def parse_agent_live_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def _repeat_count(args: argparse.Namespace) -> int:
    raw = getattr(args, "repeat", 1)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 1
    if n < 1:
        n = 1
    return min(n, MAX_TASK_REPEAT)


def run_agent_live(
    args: argparse.Namespace,
    *,
    runtime: LiveRuntime | None = None,
    printer: Callable[[str], None] = print,
) -> int:
    skill_name = args.skill
    task_name = getattr(args, "task", None)
    if skill_name is not None and task_name is not None:
        printer(
            json.dumps(
                {"ok": False, "aborted": "skill_and_task_mutex", "mode": "observe-only"},
                ensure_ascii=False,
            )
        )
        return 2
    want_hid = skill_name is not None or task_name is not None
    if want_hid and not (args.live and args.danger_confirmed):
        printer(
            json.dumps(
                {
                    "ok": False,
                    "aborted": "live_flags_required",
                    "mode": "observe-only",
                    "hint": "HID skill/task needs --live --danger-confirmed",
                },
                ensure_ascii=False,
            )
        )
        return 2
    if runtime is None:
        if want_hid:
            runtime, why = _build_hid_runtime(args)
            if runtime is None:
                mode = "task" if task_name is not None else "skill"
                printer(json.dumps({"ok": False, "aborted": why, "mode": mode}, ensure_ascii=False))
                return 2
        else:
            runtime = _build_observe_runtime(args)
            if runtime is None:
                printer(
                    json.dumps(
                        {
                            "ok": False,
                            "aborted": "observe_runtime_unavailable",
                            "mode": "observe-only",
                        },
                        ensure_ascii=False,
                    )
                )
                return 2

    printer(_startup_text(args, runtime, want_hid, task_name))
    if task_name is not None:
        return _run_task_mode(args, runtime, printer, task_name)
    result_reason = None
    try:
        if want_hid:
            name, kwargs = SKILL_ALIASES[skill_name]
            if name == "open_npc_dialog":
                kwargs = {"npc_name": args.npc_name}
            started = runtime.start_skill(name, **kwargs)
            result_reason = started.reason
            if started.status.value == "aborted":
                return _finish(printer, runtime, result_reason, 3)
        for _ in range(max(int(args.ticks), 1)):
            tick = runtime.tick()
            if tick is not None and tick.terminal:
                result_reason = tick.reason
                break
            if runtime.mode is AgentMode.ABORTED:
                result_reason = None if runtime.last_result is None else runtime.last_result.reason
                break
    finally:
        runtime.shutdown()
    return _finish(printer, runtime, result_reason, 0)


def _startup_text(
    args: argparse.Namespace,
    runtime: LiveRuntime,
    want_hid: bool,
    task_name: str | None = None,
) -> str:
    if task_name is not None:
        mode = "task"
    elif want_hid:
        mode = "skill"
    else:
        mode = "observe-only"
    payload: dict[str, Any] = {
        "startup": True,
        "mode": mode,
        "live": bool(args.live),
        "danger_confirmed": bool(args.danger_confirmed),
        "window_id": args.window_id,
        "target_pid": args.target_pid,
        "skill": args.skill,
        "task": task_name,
        "repeat": _repeat_count(args) if task_name is not None else 1,
        "ticks": args.ticks,
        "farm": False,
        "quest_loop": False,
        "runtime": runtime.summary(),
    }
    return json.dumps(payload, ensure_ascii=False)


def _task_tick_budget(args: argparse.Namespace) -> int:
    ticks = max(int(args.ticks), 1)
    if ticks == 8:
        return DEFAULT_TASK_TICK_BUDGET
    return ticks


def _run_task_mode(
    args: argparse.Namespace,
    runtime: LiveRuntime,
    printer: Callable[[str], None],
    task_name: str,
) -> int:
    repeats = _repeat_count(args)
    budget = _task_tick_budget(args)
    runner = TaskRunner(runtime)
    runs: list[dict[str, object]] = []
    last_reason: str | None = None
    last_status = TaskStatus.FAILED
    try:
        for index in range(repeats):
            if task_name != "guide-open-close":
                last_reason = "unknown_task"
                last_status = TaskStatus.FAILED
                break
            task = GuideInteractionTask(npc_name=str(args.npc_name))
            started = runner.start(task)
            result = started if started.terminal else runner.run_until_done(max_ticks=budget, sleeper=runtime._sleeper)
            last_status = result.status
            last_reason = result.reason
            runs.append(
                {
                    "index": index,
                    "task": task.name,
                    "status": result.status.value,
                    "reason": result.reason,
                    "trace": list(getattr(task, "trace", [])),
                }
            )
            if result.status is TaskStatus.ABORTED:
                break
    finally:
        runtime.shutdown()
    summary = runtime.summary()
    aborted = last_status is TaskStatus.ABORTED
    summary["ok"] = last_status is TaskStatus.SUCCESS and not aborted
    summary["finish_reason"] = last_reason or summary.get("last_reason")
    summary["task"] = task_name
    summary["task_status"] = last_status.value
    summary["task_runs"] = runs
    summary["repeat"] = len(runs)
    printer(json.dumps(summary, ensure_ascii=False))
    return 3 if aborted else 0


def _finish(printer: Callable[[str], None], runtime: LiveRuntime, reason: str | None, code: int) -> int:
    summary = runtime.summary()
    summary["ok"] = code == 0 and summary.get("last_status") != "aborted"
    summary["finish_reason"] = reason or summary.get("last_reason")
    printer(json.dumps(summary, ensure_ascii=False))
    return code


def _build_hid_runtime(args: argparse.Namespace) -> tuple[LiveRuntime | None, str]:
    if not (args.live and args.danger_confirmed):
        return None, "live_flags_required"
    if args.window_id is None or args.target_pid is None:
        return None, "window_or_pid_required"
    from l2_brain.io.cgevent_backend import CGEventInputBackend
    from l2_brain.io.focus import is_allowed_frontmost
    from l2_brain.live.perception import PerceptionHub
    from l2_brain.live.s4_probe import SCKGrabber, s4_input_profile
    from l2_brain.vision.hud_parser import HUDParser

    grabber = SCKGrabber(window_id=int(args.window_id))
    try:
        grabber.start()
    except Exception:
        return None, "capture_start_failed"
    backend = CGEventInputBackend(
        int(args.target_pid),
        live_confirmed=True,
        live_danger_confirmed=True,
        profile=s4_input_profile(),
        focus_probe=is_allowed_frontmost,
    )
    hub = PerceptionHub(
        HUDParser.from_profile(args.profile),
        focus_probe=backend.check_window_focus,
        frames=grabber,
    )
    return LiveRuntime(hub, backend=backend), "ok"


def _build_observe_runtime(args: argparse.Namespace) -> LiveRuntime | None:
    """Capture + perception only. Never constructs CGEventInputBackend."""
    if args.window_id is None:
        return None
    try:
        from l2_brain.live.perception import PerceptionHub
        from l2_brain.live.s4_probe import SCKGrabber
        from l2_brain.vision.hud_parser import HUDParser
    except Exception:
        return None
    grabber = SCKGrabber(window_id=int(args.window_id))
    try:
        grabber.start()
    except Exception:
        return None
    hub = PerceptionHub(
        HUDParser.from_profile(args.profile),
        focus_probe=lambda: True,
        frames=grabber,
    )
    return LiveRuntime(hub, backend=None)
