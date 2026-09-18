"""Peaceful NPC dialog probe. Hod 85. Orchestrates LiveRuntime skills. Not Frozen L1."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from l2_brain.bench.h8_latency_bench import summarize
from l2_brain.calibration.frame_sync import write_png
from l2_brain.capture.errors import CaptureError
from l2_brain.capture.helper import list_windows, resolve_helper
from l2_brain.experiment.clocks import mono_ns
from l2_brain.io.cgevent_backend import CGEventInputBackend
from l2_brain.io.focus import frontmost_app, is_allowed_frontmost
from l2_brain.live.s4_probe import (
    SCKGrabber,
    TICK_S,
    _ms,
    s4_input_profile,
)
from l2_brain.vision.dialog_parser import extract_menu_items, is_dialog_open
from l2_brain.vision.hud_parser import HUDParser

DEFAULT_PROFILE = Path("config/window_profiles/parallels_l2.json")
DEFAULT_OUT = Path("docs/evidence/live-s4/npc-dialog-probe.json")
DEFAULT_PNG = Path("run/npc_dialog_detected.png")
DEFAULT_LAST_PNG = Path("run/npc_dialog_last.png")
DEFAULT_LOCKED_PNG = Path("run/npc_dialog_locked.png")
LOCK_S = 3.0
SETTLE_S = 0.60
APPROACH_S = 2.0
TALK_WAIT_S = 1.5
ITEM_PAUSE_S = 0.60
ESC_PAUSE_S = 0.40
TALK_NX = 0.50
TALK_NY = 0.48
CHAT_LINK_MAX = 12
MAX_CAPTURE_RESTARTS = 24
FORBIDDEN_SLOTS = frozenset({"F1", "F3", "F4"})
DEFAULT_NPC_NAME = "Newbie Guide"


def run_npc_dialog_probe(
    *,
    live: bool,
    danger_confirmed: bool,
    window_id: int | None = None,
    target_pid: int | None = None,
    slot: str = "F5",
    via_chat: bool = False,
    runtime_validation: bool = False,
    npc_name: str = DEFAULT_NPC_NAME,
    profile_path: Path = DEFAULT_PROFILE,
    out_path: Path | None = DEFAULT_OUT,
    png_path: Path = DEFAULT_PNG,
    last_png_path: Path = DEFAULT_LAST_PNG,
    locked_png_path: Path = DEFAULT_LOCKED_PNG,
    grabber: Any | None = None,
    backend: CGEventInputBackend | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    now_ns: Callable[[], int] | None = None,
    focus_probe: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    from l2_brain.live.perception import PerceptionHub
    from l2_brain.live.runtime import LiveRuntime
    from l2_brain.live.runtime_validation import NPC_ID, npc_validation_result, stamp_runtime_identity
    from l2_brain.live.skills.result import SkillStatus

    if runtime_validation:
        via_chat = True

    clock = now_ns or mono_ns
    started = clock()
    key = str(slot or "F5").upper()
    if key in FORBIDDEN_SLOTS or key == "F2":
        key = "F5"
    slot_n = int(key[1:]) if key.startswith("F") and key[1:].isdigit() else 5
    steps: list[dict[str, Any]] = []
    payload: dict[str, Any] = {
        "ok": False,
        "s4_open": True,
        "npc_dialog": True,
        "farm": False,
        "combat": False,
        "heal_sent": False,
        "live": bool(live and danger_confirmed),
        "hid_sent": False,
        "aborted": None,
        "window_id": window_id,
        "target_pid": target_pid,
        "slot": None if via_chat else key,
        "via_chat": bool(via_chat),
        "npc_name": npc_name if via_chat else None,
        "chat_command": None,
        "chat_target_success": False,
        "dialog_was_closed": False,
        "dialog_opened_from_closed": False,
        "f2_approach": False,
        "sck_crashes": 0,
        "target_acquired": False,
        "approach_time_sec": None,
        "dialog_detected": False,
        "dialog_confidence": None,
        "dialog_reason": None,
        "talk_click_dispatched": False,
        "talk_click_xy": None,
        "talk_clicks": 0,
        "click_dispatched": False,
        "click_xy": None,
        "link_kind": None,
        "quest_link_clicks": 0,
        "guide_link_count": 0,
        "guide_items_opened": 0,
        "total_items_found": 0,
        "items_clicked": 0,
        "menu_item_xy": [],
        "false_target_markers": 0,
        "escape_sent": False,
        "png": None,
        "last_png": None,
        "locked_png": None,
        "capture_restarts": 0,
        "capture_error": None,
        "capture_lost_reason": None,
        "parse_dialog_ms": [],
        "ticks": 0,
        "steps": steps,
        "events": [],
        "stuck_keys_count": 0,
        "watchdog_tripped": False,
        "runtime_validation": bool(runtime_validation),
        "skill_trace": [],
        "target_by_name_started": False,
        "target_locked": False,
        "open_dialog_skill_started": False,
        "open_dialog_skill_status": None,
        "talk_click_sent": False,
        "dialog_items_count": 0,
        "clicked_item_index": None,
        "click_skill_status": None,
        "close_dialog_status": None,
        "dialog_closed": False,
        "capture_restart_attempts": 0,
        "capture_restart_successes": 0,
        "capture_recovery_used": False,
        "focus_lost": False,
        "capture_lost": False,
        "runtime_abort_reason": None,
        "release_all_called": False,
        "validation_result": None,
        "elapsed_sec": 0.0,
    }
    stamp_runtime_identity(payload, validation_id=NPC_ID)
    payload["npc_name"] = npc_name
    if not live or not danger_confirmed:
        payload["aborted"] = "live_flags_required"
        return _finish(payload, out_path, clock, started, None)
    if grabber is None and (window_id is None or int(window_id) < 1):
        payload["aborted"] = "window_id_required"
        return _finish(payload, out_path, clock, started, None)

    parser = HUDParser.from_profile(profile_path)
    own_grabber = grabber is None
    own_backend = backend is None
    grabber = grabber or SCKGrabber(int(window_id or 0), latest_timeout_s=0.8)
    origin = _window_origin(window_id)
    if own_backend:
        pid = int(target_pid or 0)
        if pid < 1:
            info = frontmost_app()
            pid = int(info.pid) if info is not None else 0
        if pid < 1:
            payload["aborted"] = "no_target_pid"
            return _finish(payload, out_path, clock, started, None)
        payload["target_pid"] = pid
        backend = CGEventInputBackend(
            pid,
            live_confirmed=True,
            live_danger_confirmed=True,
            profile=s4_input_profile(),
            focus_probe=focus_probe or is_allowed_frontmost,
            window_origin=origin,
        )
    assert backend is not None
    if origin != (0.0, 0.0):
        backend.window_origin = origin
    win_w, win_h = _window_size(window_id, 0, 0)
    if win_w >= 8 and win_h >= 8:
        backend.window_size = (float(win_w), float(win_h))
    focus = focus_probe or backend.check_window_focus

    def add_step(name: str, **extra: Any) -> None:
        row = {"step": name, "t_ms": _ms(clock(), started), **extra}
        steps.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    def note_capture(exc: BaseException) -> None:
        payload["capture_error"] = f"{type(exc).__name__}: {exc}"[:300]
        source = getattr(grabber, "source", None)
        lost = getattr(source, "_lost", None)
        err = getattr(source, "_stderr", None)
        if lost:
            payload["capture_lost_reason"] = str(lost)[:300]
        if err:
            payload["capture_stderr"] = str(err)[:400]

    def restart_capture(why: str) -> bool:
        payload["capture_restart_attempts"] = int(payload.get("capture_restart_attempts") or 0) + 1
        if int(payload.get("capture_restarts") or 0) >= MAX_CAPTURE_RESTARTS:
            return False
        closer = getattr(grabber, "close", None)
        starter = getattr(grabber, "start", None)
        if closer is None or starter is None:
            return False
        try:
            closer()
        except Exception:
            pass
        try:
            starter()
        except (CaptureError, RuntimeError) as exc:
            note_capture(exc)
            return False
        payload["capture_restarts"] = int(payload.get("capture_restarts") or 0) + 1
        payload["capture_restart_successes"] = int(payload.get("capture_restart_successes") or 0) + 1
        payload["capture_recovery_used"] = True
        if why in {"sense", "dialog_wait"}:
            payload["sck_crashes"] = int(payload.get("sck_crashes") or 0) + 1
        add_step("capture_restart", why=why, n=payload["capture_restarts"])
        return True

    def recover_capture() -> bool:
        return restart_capture("sense")

    hub = PerceptionHub(parser, focus_probe=focus, frames=grabber, now_ns=clock)
    runtime: LiveRuntime | None = LiveRuntime(
        hub,
        backend=backend,
        clock=clock,
        sleeper=sleeper,
        window_size=(win_w, win_h) if win_w >= 8 and win_h >= 8 else None,
        log=payload,
        recover_capture=recover_capture,
    )

    def sync_payload() -> None:
        payload["_image"] = hub.last_image
        payload["_hud"] = hub.last_hud
        payload["_dialog"] = hub.last_dialog
        payload["_html_open"] = bool(runtime.state.dialog_open)
        if hub.last_parse_dialog_ms is not None:
            payload["parse_dialog_ms"].append(hub.last_parse_dialog_ms)
        image = hub.last_image
        if image is not None:
            image_h, image_w = image.shape[:2]
            sized = _window_size(window_id, image_w, image_h)
            runtime.window_size = sized
            if sized[0] >= 8 and sized[1] >= 8:
                backend.window_size = (float(sized[0]), float(sized[1]))

    def sense() -> Any:
        if not focus():
            payload["aborted"] = "focus_lost"
            return None
        state = runtime.observe()
        if not state.focus_ok:
            payload["aborted"] = "focus_lost"
            return None
        if not state.capture_ok:
            payload["aborted"] = "capture_lost"
            return None
        payload["ticks"] = int(payload["ticks"]) + 1
        sync_payload()
        payload["target_locked"] = bool(state.target_locked is True)
        if state.dialog_items:
            payload["dialog_items_count"] = len(state.dialog_items)
        return hub.last_hud

    def pause(seconds: float) -> bool:
        until = clock() + int(seconds * 1_000_000_000)
        while clock() < until:
            if payload.get("aborted"):
                return True
            sleeper(TICK_S)
            if sense() is None:
                return True
        return bool(payload.get("aborted"))

    def play(name: str, **kwargs: object) -> Any:
        if name == "open_npc_dialog":
            payload["open_dialog_skill_started"] = True
            payload["target_by_name_started"] = True
        if name == "talk_click":
            payload["talk_click_sent"] = True
        result = runtime.run_skill(name, **kwargs)
        sync_payload()
        if name == "open_npc_dialog":
            payload["open_dialog_skill_status"] = result.status.value
            if result.data.get("talk_clicked"):
                payload["talk_click_sent"] = True
            payload["target_locked"] = bool(runtime.state.target_locked is True or payload.get("chat_target_success"))
        if name == "click_dialog_item":
            payload["click_skill_status"] = result.status.value
            payload["clicked_item_index"] = kwargs.get("index", payload.get("clicked_item_index"))
        if name == "close_dialog":
            payload["close_dialog_status"] = result.status.value
        if result.reason in {"focus_lost", "capture_lost", "kill_switch"}:
            payload["aborted"] = result.reason
        return result

    def note_dialog(*, approach_s: float, already: bool = False) -> None:
        dialog = payload.get("_dialog")
        payload["dialog_detected"] = True
        if dialog is not None:
            payload["dialog_confidence"] = float(dialog.confidence)
            payload["dialog_reason"] = dialog.reason
        payload["approach_time_sec"] = approach_s
        add_step(
            "dialog_open",
            confidence=payload.get("dialog_confidence"),
            reason=payload.get("dialog_reason"),
            approach_s=approach_s,
            already_open=already,
        )

    def note_talk(result: Any) -> None:
        payload["talk_click_dispatched"] = True
        payload["talk_clicks"] = int(payload["talk_clicks"]) + 1
        x = result.data.get("x")
        y = result.data.get("y")
        if x is not None and y is not None:
            payload["talk_click_xy"] = [int(x), int(y)]
            add_step("approach", via="skill", x=int(x), y=int(y), nx=TALK_NX, ny=TALK_NY)

    def dialog_is_open() -> bool:
        if payload.get("_html_open"):
            return True
        dialog = payload.get("_dialog")
        return bool(dialog is not None and dialog.open)

    def reopen_dialog() -> bool:
        if sense() is None:
            return False
        if payload.get("_html_open"):
            return True
        locked = bool(runtime.state.target_locked is True)
        result = play("open_npc_dialog", npc_name=npc_name, retarget=via_chat and not locked)
        if result.status is not SkillStatus.SUCCESS:
            return False
        if result.data.get("f2_approach"):
            payload["f2_approach"] = True
        if result.data.get("talk_clicked"):
            payload["talk_click_dispatched"] = True
            payload["talk_clicks"] = int(payload["talk_clicks"]) + 1
        return dialog_is_open()

    def crawl_menu() -> bool:
        image = payload.get("_image")
        if image is None:
            payload["aborted"] = "no_frame"
            return False
        items = extract_menu_items(image)
        payload["false_target_markers"] = 0
        if any(x / max(image.shape[1], 1) > 0.42 for x, _y in items):
            payload["false_target_markers"] = 1
        payload["total_items_found"] = len(items)
        payload["guide_link_count"] = len(items)
        payload["dialog_items_count"] = len(items)
        payload["menu_item_xy"] = [[int(x), int(y)] for x, y in items]
        add_step("guide_menu", n=len(items), items=payload["menu_item_xy"])
        need = 1 if runtime_validation else 2
        if len(items) < need:
            payload["aborted"] = "no_link"
            add_step("abort", reason="no_link")
            return False
        click_limit = 1 if runtime_validation else CHAT_LINK_MAX
        for index, (px, py) in enumerate(items[:click_limit]):
            if sense() is None:
                add_step("abort", reason=payload.get("aborted"))
                return False
            if not payload.get("_html_open"):
                if not reopen_dialog():
                    payload["aborted"] = payload.get("aborted") or "dialog_reopen_failed"
                    add_step("abort", reason=payload["aborted"], item=index)
                    return False
            clicked = play("click_dialog_item", index=index, x=int(px), y=int(py))
            if clicked.status is not SkillStatus.SUCCESS:
                add_step("abort", reason=payload.get("aborted") or clicked.reason)
                return False
            payload["click_dispatched"] = True
            payload["click_xy"] = [int(px), int(py)]
            payload["link_kind"] = "blue"
            payload["quest_link_clicks"] = int(payload["quest_link_clicks"]) + 1
            payload["guide_items_opened"] = int(payload["guide_items_opened"]) + 1
            payload["items_clicked"] = int(payload["items_clicked"]) + 1
            n = int(payload["items_clicked"])
            _write_debug_png(
                payload.get("_image"),
                png_path.with_name(f"{png_path.stem}_item{n}{png_path.suffix}"),
                payload,
                f"item_png_{n}",
            )
            add_step("guide_item", index=index, x=int(px), y=int(py), px=px, py=py)
            if pause(ITEM_PAUSE_S) and payload.get("aborted"):
                add_step("abort", reason=payload["aborted"])
                return False
            closed = play("close_dialog")
            if closed.status is SkillStatus.ABORTED:
                add_step("abort", reason=payload.get("aborted") or "escape_failed")
                return False
            payload["escape_sent"] = True
            add_step("Escape", hid_sent=True, after_item=index)
            if pause(ESC_PAUSE_S) and payload.get("aborted"):
                add_step("abort", reason=payload["aborted"])
                return False
        return True

    try:
        if not focus():
            payload["aborted"] = "focus_not_parallels"
            add_step("abort", reason="focus_not_parallels")
            return _finish(payload, out_path, clock, started, backend)
        grabber.start()
        add_step(
            "npc_start",
            slot=None if via_chat else key,
            via_chat=via_chat,
            npc_name=npc_name if via_chat else None,
            farm=False,
        )
        if sense() is None or payload.get("aborted"):
            add_step("abort", reason=payload.get("aborted"))
            return _finish(payload, out_path, clock, started, backend)
        if pause(SETTLE_S) and payload.get("aborted"):
            add_step("abort", reason=payload["aborted"])
            return _finish(payload, out_path, clock, started, backend)
        if via_chat:
            if not _ensure_dialog_closed(payload, runtime, pause, add_step, play):
                return _finish(payload, out_path, clock, started, backend, last_png_path)
            opened = play("open_npc_dialog", npc_name=npc_name, retarget=True)
            if opened.status is not SkillStatus.SUCCESS:
                payload["aborted"] = payload.get("aborted") or opened.reason or "chat_target_failed"
                add_step("abort", reason=payload["aborted"])
                return _finish(payload, out_path, clock, started, backend, last_png_path)
            payload["target_acquired"] = True
            payload["chat_target_success"] = bool(payload.get("chat_target_success"))
            hud = payload.get("_hud")
            add_step("target_acquired", via="chat", target_hp=getattr(hud, "target_hp_ratio", None))
            _write_debug_png(payload.get("_image"), locked_png_path, payload, "locked_png")
            if opened.data.get("f2_approach"):
                payload["f2_approach"] = True
            if opened.data.get("talk_clicked"):
                note_talk(opened)
                payload["talk_click_sent"] = True
            approach_from = clock()
            if dialog_is_open():
                note_dialog(approach_s=_ms(clock(), approach_from) / 1000.0)
                if payload.get("dialog_was_closed"):
                    payload["dialog_opened_from_closed"] = True
            else:
                payload["aborted"] = payload.get("aborted") or "dialog_timeout"
                payload["approach_time_sec"] = _ms(clock(), approach_from) / 1000.0
                add_step("abort", reason=payload["aborted"], approach_s=payload["approach_time_sec"])
                return _finish(payload, out_path, clock, started, backend, last_png_path)
        else:
            tapped = play("tap_hotkey", key=key, slot=slot_n)
            if tapped.status is not SkillStatus.SUCCESS:
                add_step("abort", reason=payload.get("aborted") or tapped.reason)
                return _finish(payload, out_path, clock, started, backend)
            add_step(key, hid_sent=True, slot=slot_n)
            locked = False
            until = clock() + int(LOCK_S * 1_000_000_000)
            while clock() < until and not payload.get("aborted"):
                sleeper(TICK_S)
                parsed = sense()
                if parsed is None:
                    break
                if runtime.state.target_locked is True:
                    locked = True
                    payload["target_acquired"] = True
                    add_step("target_acquired", target_hp=runtime.state.target_hp)
                    _write_debug_png(payload.get("_image"), locked_png_path, payload, "locked_png")
                    break
            if not locked:
                payload["aborted"] = payload.get("aborted") or "no_target"
                add_step("abort", reason=payload["aborted"])
                return _finish(payload, out_path, clock, started, backend, last_png_path)
            approach_from = clock()
            opened_now = False
            if dialog_is_open():
                opened_now = True
                note_dialog(approach_s=0.0, already=True)
            if not opened_now:
                talked = play("talk_click")
                if talked.status is SkillStatus.ABORTED:
                    add_step("abort", reason=payload.get("aborted") or talked.reason)
                    return _finish(payload, out_path, clock, started, backend, last_png_path)
                note_talk(talked)
                opened_now = dialog_is_open() or talked.status is SkillStatus.SUCCESS
                if opened_now:
                    note_dialog(approach_s=_ms(clock(), approach_from) / 1000.0)
            if not opened_now:
                payload["aborted"] = payload.get("aborted") or "dialog_timeout"
                payload["approach_time_sec"] = _ms(clock(), approach_from) / 1000.0
                add_step("abort", reason=payload["aborted"], approach_s=payload["approach_time_sec"])
                return _finish(payload, out_path, clock, started, backend, last_png_path)
        image = payload.get("_image")
        if image is not None:
            png_path.parent.mkdir(parents=True, exist_ok=True)
            write_png(png_path, image)
            payload["png"] = str(png_path)
            add_step("png", path=str(png_path))
        if via_chat:
            if not crawl_menu():
                return _finish(payload, out_path, clock, started, backend, last_png_path)
            if sense() is not None:
                payload["dialog_closed"] = not dialog_is_open()
        else:
            dialog = payload.get("_dialog")
            image = payload.get("_image")
            click = dialog.first_link if dialog is not None and image is not None else None
            items = list(runtime.state.dialog_items) if runtime.state.dialog_items else []
            if click is None and items:
                click = items[0]
            if click is None or image is None:
                payload["aborted"] = "no_link"
                add_step("abort", reason="no_link")
                return _finish(payload, out_path, clock, started, backend, last_png_path)
            link = play("click_dialog_item", index=0, x=int(click[0]), y=int(click[1]))
            if link.status is not SkillStatus.SUCCESS:
                add_step("abort", reason=payload.get("aborted") or link.reason)
                return _finish(payload, out_path, clock, started, backend, last_png_path)
            payload["click_dispatched"] = True
            payload["click_xy"] = [int(click[0]), int(click[1])]
            payload["link_kind"] = getattr(dialog, "link_kind", None) if dialog is not None else None
            payload["quest_link_clicks"] = 1
            closed = play("close_dialog")
            if closed.status is SkillStatus.ABORTED:
                add_step("abort", reason=payload.get("aborted") or "escape_failed")
                return _finish(payload, out_path, clock, started, backend, last_png_path)
            payload["escape_sent"] = True
            add_step("Escape", hid_sent=True)
            if sense() is not None:
                payload["dialog_closed"] = not dialog_is_open()
        if runtime_validation:
            payload["ok"] = False
        elif via_chat:
            payload["ok"] = bool(
                payload.get("chat_target_success")
                and payload.get("dialog_opened_from_closed")
                and payload.get("f2_approach")
                and int(payload.get("items_clicked") or 0) >= int(payload.get("total_items_found") or 1)
                and int(payload.get("total_items_found") or 0) >= 2
                and int(payload.get("false_target_markers") or 0) == 0
            )
        else:
            payload["ok"] = True
        add_step(
            "validation_pending" if runtime_validation else ("SUCCESS" if payload["ok"] else "abort"),
            farm=False,
            items_clicked=payload.get("items_clicked"),
            total_items_found=payload.get("total_items_found"),
        )
        return _finish(payload, out_path, clock, started, backend, last_png_path)
    except Exception as exc:  # noqa: BLE001 — always release HID
        payload["aborted"] = payload.get("aborted") or f"error:{type(exc).__name__}"
        add_step("abort", reason=payload["aborted"], error=str(exc)[:200])
        return _finish(payload, out_path, clock, started, backend, last_png_path)
    finally:
        payload.pop("_image", None)
        payload.pop("_hud", None)
        payload.pop("_dialog", None)
        payload.pop("_html_open", None)
        if runtime is not None:
            runtime.shutdown()
        if own_grabber:
            grabber.close()


def _ensure_dialog_closed(
    payload: dict[str, Any],
    runtime: Any,
    pause: Callable[[float], bool],
    add_step: Callable[..., None],
    play: Callable[..., Any],
) -> bool:
    from l2_brain.live.skills.result import SkillStatus

    if payload.get("_html_open"):
        closed = play("close_dialog")
        if closed.status is SkillStatus.ABORTED:
            add_step("abort", reason=payload.get("aborted") or "escape_failed")
            return False
        if pause(0.35) and payload.get("aborted"):
            add_step("abort", reason=payload["aborted"])
            return False
    image = payload.get("_image")
    if image is not None and is_dialog_open(image):
        payload["aborted"] = "dialog_still_open"
        add_step("abort", reason="dialog_still_open")
        return False
    payload["dialog_was_closed"] = True
    add_step("dialog_closed")
    return True


def _window_origin(window_id: int | None) -> tuple[float, float]:
    row = _window_row(window_id)
    if row is None:
        return (0.0, 0.0)
    return (float(row.get("x") or 0.0), float(row.get("y") or 0.0))


def _window_size(window_id: int | None, fallback_w: int, fallback_h: int) -> tuple[int, int]:
    row = _window_row(window_id)
    if row is None:
        return (int(fallback_w), int(fallback_h))
    return (int(row.get("width") or fallback_w), int(row.get("height") or fallback_h))


def _window_row(window_id: int | None) -> dict[str, Any] | None:
    if window_id is None:
        return None
    try:
        data = list_windows(resolve_helper(build=False))
    except (OSError, RuntimeError, ValueError):
        return None
    for row in data.get("windows") or ():
        if int(row.get("id") or 0) == int(window_id):
            return dict(row)
    return None


def _write_debug_png(image: Any, path: Path | None, payload: dict[str, Any], key: str) -> None:
    if image is None or path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_png(path, image)
    payload[key] = str(path)


def _finish(
    payload: dict[str, Any],
    out_path: Path | None,
    clock: Callable[[], int],
    started: int,
    backend: CGEventInputBackend | None,
    last_png_path: Path | None = None,
) -> dict[str, Any]:
    from l2_brain.live.s4_probe import _finish as finish_probe
    from l2_brain.live.runtime_validation import npc_validation_result

    if not payload.get("ok"):
        _write_debug_png(payload.get("_image"), last_png_path, payload, "last_png")
    payload.pop("_image", None)
    payload.pop("_hud", None)
    payload.pop("_dialog", None)
    payload.pop("_html_open", None)
    times = list(payload.pop("parse_dialog_ms", []))
    payload["parse_dialog"] = summarize(times)
    if backend is not None:
        payload["release_all_called"] = any(row.reason == "release_all" for row in backend.log)
    finished = finish_probe(payload, out_path, clock, started, backend)
    finished["elapsed_time_sec"] = float(finished.get("session_ms") or 0.0) / 1000.0
    finished["elapsed_sec"] = float(finished["elapsed_time_sec"])
    if backend is not None:
        finished["release_all_called"] = bool(
            finished.get("release_all_called")
            or any(row.reason == "release_all" for row in backend.log)
        )
    if finished.get("runtime_validation"):
        finished["validation_result"] = npc_validation_result(finished)
        finished["ok"] = finished["validation_result"] == "PASS"
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(finished, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return finished
