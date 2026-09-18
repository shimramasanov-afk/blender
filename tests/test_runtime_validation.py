import inspect

from l2_brain.cli import main
from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster
from l2_brain.live.npc_dialog_probe import run_npc_dialog_probe
from l2_brain.live.runtime import LiveRuntime
from l2_brain.live.runtime_validation import npc_validation_result
from l2_brain.live.s4_probe import ScriptedGrabber
from l2_brain.live.spot_loop import run_integrated_spot

from test_npc_dialog import _Clock, _html_scene, _scene, _write_profile
from test_spot_loop import _backend, _f2, _f3, _scene as _spot_scene, _write_profile as _write_spot_profile


def test_validation_banner_without_live_flags(tmp_path, capsys) -> None:
    out = tmp_path / "r1.json"
    code = main(
        [
            "s4-npc-dialog",
            "--runtime-validation",
            "--via-chat",
            "--out",
            str(out),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "LIVE RUNTIME VALIDATION" in captured.out
    assert "F12 stop" in captured.out
    assert "live_flags_required" in out.read_text(encoding="utf-8")


def test_npc_validation_clicks_one_item_and_records_trace(tmp_path) -> None:
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

    class _Val(ScriptedGrabber):
        def latest_image(self):
            clicks = sum(1 for row in backend.log if row.action_type == "GroundClick")
            chat_ok = any(row.reason == "type_text" and row.key == "/" for row in backend.log)
            sent = sum(1 for row in backend.log if row.key == "return") >= 4
            f2 = sum(1 for row in backend.log if row.key == "F2")
            escaped = any(row.key == "escape" for row in backend.log)
            if escaped and clicks >= 2:
                return locked
            if clicks >= 1 and chat_ok and f2 >= 1:
                return dialog
            if sent and chat_ok:
                return locked
            return idle

    payload = run_npc_dialog_probe(
        live=True,
        danger_confirmed=True,
        via_chat=True,
        runtime_validation=True,
        npc_name="Newbie Guide",
        grabber=_Val([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "R1-runtime-npc.json",
        png_path=tmp_path / "npc_dialog_detected.png",
        last_png_path=tmp_path / "npc_dialog_last.png",
        locked_png_path=tmp_path / "npc_dialog_locked.png",
    )
    assert payload["architecture"] == "LiveRuntime"
    assert payload["runtime_used"] is True
    assert payload["validation_id"] == "R1"
    assert payload["items_clicked"] == 1
    assert payload["total_items_found"] >= 2
    assert payload["open_dialog_skill_status"] == "success"
    assert payload["click_skill_status"] == "success"
    assert payload["talk_click_sent"] is True
    assert payload["dialog_detected"] is True
    assert payload["dialog_closed"] is True
    assert payload["validation_result"] == "PASS"
    assert payload["ok"] is True
    assert payload["capture_recovery_used"] is False
    names = [row["skill"] for row in payload["skill_trace"]]
    assert "open_npc_dialog" in names
    assert "click_dialog_item" in names
    assert "close_dialog" in names
    assert payload["release_all_called"] is True
    assert not any(row.key in ("F1", "F3", "F5") for row in backend.log)


def test_npc_validation_partial_if_dialog_stays_open(tmp_path) -> None:
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

    class _Stay(ScriptedGrabber):
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
        runtime_validation=True,
        grabber=_Stay([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "R1-partial.json",
        png_path=tmp_path / "npc_dialog_detected.png",
        last_png_path=tmp_path / "npc_dialog_last.png",
        locked_png_path=tmp_path / "npc_dialog_locked.png",
    )
    assert payload["dialog_detected"] is True
    assert payload["dialog_closed"] is False
    assert payload["validation_result"] == "PARTIAL"
    assert payload["ok"] is False


def test_npc_validation_f2_dialog_without_talk_click_is_pass() -> None:
    payload = {
        "open_dialog_skill_status": "success",
        "click_skill_status": "success",
        "close_dialog_status": "success",
        "dialog_detected": True,
        "dialog_items_count": 2,
        "dialog_closed": True,
        "runtime_used": True,
        "target_acquired": True,
        "chat_target_success": True,
        "talk_click_sent": False,
        "talk_click_dispatched": False,
        "f2_approach": True,
        "release_all_called": True,
        "aborted": None,
        "focus_lost": False,
        "capture_restart_successes": 6,
    }
    assert npc_validation_result(payload) == "PASS"
    assert payload["capture_recovery_used"] is True


def test_legacy_via_chat_still_clicks_all_items(tmp_path) -> None:
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
        grabber=_Chat([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "legacy.json",
        png_path=tmp_path / "npc_dialog_detected.png",
        last_png_path=tmp_path / "npc_dialog_last.png",
        locked_png_path=tmp_path / "npc_dialog_locked.png",
    )
    assert payload["ok"] is True
    assert payload["items_clicked"] == payload["total_items_found"]
    assert payload["items_clicked"] >= 3
    assert payload.get("validation_result") is None


def test_combat_validation_fields_one_kill(tmp_path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    idle = _spot_scene(hp=0.95, target=False)
    live = _spot_scene(hp=0.95, target=True, target_hp=0.90)
    dead = _spot_scene(hp=0.95, target=True, target_hp=0.0)

    class _Aware(ScriptedGrabber):
        def latest_image(self):
            last_esc = max((i for i, row in enumerate(backend.log) if row.key == "escape"), default=-1)
            last_f1 = max(
                (i for i, row in enumerate(backend.log) if row.action_type == "TargetSelect"),
                default=-1,
            )
            if _f2(backend) // 2 > _f3(backend) // 3:
                return dead
            if last_f1 > last_esc:
                return live
            return idle

    payload = run_integrated_spot(
        live=True,
        danger_confirmed=True,
        kills=1,
        timeout_s=None,
        runtime_validation=True,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_spot_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "R2-runtime-combat.json",
    )
    assert payload["architecture"] == "LiveRuntime"
    assert payload["runtime_used"] is True
    assert payload["kills_completed"] == 1
    assert payload["attack_skill_runs"] >= 1
    assert payload["attack_skill_success"] >= 1
    assert payload["loot_skill_runs"] >= 1
    assert payload["f2_input_count"] >= 2
    assert payload["stuck_keys"] == 0
    assert payload["release_all_called"] is True
    assert payload["farm"] is False
    assert payload["validation_result"] == "PASS"
    names = [row["skill"] for row in payload["skill_trace"]]
    assert "attack_target" in names
    assert "loot_target" in names
    src = inspect.getsource(LiveRuntime)
    assert "run_integrated_spot" not in src
