from pathlib import Path

from l2_brain.io.chat_commander import sanitize_npc_name, target_by_name
from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster
from l2_brain.live.npc_dialog_probe import run_npc_dialog_probe
from l2_brain.live.s4_probe import ScriptedGrabber

from test_npc_dialog import _Clock, _html_scene, _scene, _write_profile


def test_sanitize_npc_name() -> None:
    assert sanitize_npc_name("  Newbie   Guide\n") == "Newbie Guide"


def test_target_by_name_escape_enter_and_fail_escape() -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=poster,
        focus_probe=lambda: True,
        now_ns=clock,
    )
    payload: dict = {}
    ok = target_by_name(
        backend,
        "Newbie Guide",
        lock_probe=lambda: False,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        payload=payload,
        char_delay_s=0.0,
        lock_wait_s=0.2,
    )
    assert ok is False
    assert payload["chat_target_success"] is False
    assert payload["chat_command"] == "/target Newbie Guide"
    keys = [row.key for row in backend.log if row.key]
    assert keys[0] == "escape"
    assert keys.count("return") >= 2
    assert keys[-1] == "escape"
    assert any(row.reason == "type_text" and row.key == "/" for row in backend.log)
    assert any(row.reason == "type_text" and row.key == "N" for row in backend.log)


def test_target_by_name_probe_error_keeps_waiting() -> None:
    clock = _Clock()
    backend = CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=RecordingPoster(),
        focus_probe=lambda: True,
        now_ns=clock,
    )
    payload: dict = {}
    hits = {"n": 0}

    def probe() -> bool:
        hits["n"] += 1
        if hits["n"] == 1:
            raise RuntimeError("capture_gap")
        return True

    ok = target_by_name(
        backend,
        "Newbie Guide",
        lock_probe=probe,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        payload=payload,
        char_delay_s=0.0,
        lock_wait_s=0.2,
    )
    assert ok is True
    assert payload["chat_target_success"] is True
    assert hits["n"] >= 2


def test_target_by_name_true_when_locked() -> None:
    clock = _Clock()
    backend = CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=RecordingPoster(),
        focus_probe=lambda: True,
        now_ns=clock,
    )
    payload: dict = {}
    ok = target_by_name(
        backend,
        "Newbie Guide",
        lock_probe=lambda: True,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        payload=payload,
        char_delay_s=0.0,
        lock_wait_s=0.2,
    )
    assert ok is True
    assert payload["chat_target_success"] is True
    assert backend.log[-1].key != "escape" or backend.log[-1].reason == "type_text"


def test_probe_chat_opens_closed_dialog(tmp_path: Path) -> None:
    clock = _Clock()
    backend = CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=RecordingPoster(),
        focus_probe=lambda: True,
        now_ns=clock,
    )
    idle = _scene(locked=False)
    locked = _scene(locked=True)
    dialog = _html_scene(locked=True)

    class _Chat(ScriptedGrabber):
        def latest_image(self):
            clicks = sum(1 for row in backend.log if row.action_type == "GroundClick")
            chat_ok = any(row.reason == "type_text" and row.key == "/" for row in backend.log)
            sent = sum(1 for row in backend.log if row.key == "return") >= 4
            f2 = sum(1 for row in backend.log if row.key == "F2")
            if clicks >= 1 and chat_ok and f2 >= 1:
                return dialog
            if sent and chat_ok:
                return locked
            return idle

    payload = run_npc_dialog_probe(
        live=True,
        danger_confirmed=True,
        via_chat=True,
        npc_name="Newbie Guide",
        grabber=_Chat([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "npc.json",
        png_path=tmp_path / "npc_dialog_detected.png",
        last_png_path=tmp_path / "npc_dialog_last.png",
        locked_png_path=tmp_path / "npc_dialog_locked.png",
    )
    assert payload["ok"] is True
    assert payload["via_chat"] is True
    assert payload["chat_target_success"] is True
    assert payload["dialog_was_closed"] is True
    assert payload["dialog_opened_from_closed"] is True
    assert payload["talk_clicks"] == 1
    assert payload["f2_approach"] is True
    assert payload["items_clicked"] >= 3
    assert payload["items_clicked"] == payload["total_items_found"]
    assert payload["false_target_markers"] == 0
    assert payload["sck_crashes"] == 0
    assert sum(1 for row in backend.log if row.key == "F2") >= 1
    assert not any(row.key in ("F1", "F3", "F5") for row in backend.log)
