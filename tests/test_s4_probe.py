from pathlib import Path

import numpy as np

from l2_brain.cli import main
from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster
from l2_brain.live.s4_probe import ScriptedGrabber, run_s4_probe
from l2_brain.vision.hud_parser import HUDParser, HudLayout


class _Clock:
    def __init__(self) -> None:
        self.t = 10**12

    def __call__(self) -> int:
        return self.t

    def advance_ms(self, ms: int) -> None:
        self.t += ms * 1_000_000


def _layout() -> HudLayout:
    return HudLayout.from_mapping(
        {
            "hud": {
                "self_bars": {"norm_rect": [0.0, 0.0, 0.5, 0.3]},
                "self_cp": {"norm_rect": [0.0, 0.0, 0.5, 0.1]},
                "self_hp": {"norm_rect": [0.0, 0.1, 0.5, 0.1]},
                "self_mp": {"norm_rect": [0.0, 0.2, 0.5, 0.1]},
                "target_frame": {"norm_rect": [0.5, 0.0, 0.5, 0.3]},
                "target_hp": {"norm_rect": [0.5, 0.1, 0.5, 0.1]},
            }
        }
    )


def _scene(*, hp: float, target: bool, target_hp: float = 1.0) -> np.ndarray:
    image = np.full((100, 200, 3), 18, dtype=np.uint8)
    image[0:10, 0 : int(100 * 0.95)] = (220, 180, 20)
    image[10:20, 0 : int(100 * hp)] = (220, 20, 20)
    image[20:30, 0:100] = (20, 40, 220)
    if target:
        image[0:30, 100:200] = (40, 32, 28)
        image[10:20, 100 : 100 + int(100 * target_hp)] = (220, 20, 20)
    return image


def _backend(clock: _Clock, poster: RecordingPoster | None = None, focus: bool = True) -> CGEventInputBackend:
    return CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=poster or RecordingPoster(),
        focus_probe=lambda: focus,
        now_ns=clock,
    )


def _write_profile(path: Path) -> Path:
    HUDParser(_layout())
    payload = {
        "hud": {
            "self_bars": {"norm_rect": [0.0, 0.0, 0.5, 0.3]},
            "self_cp": {"norm_rect": [0.0, 0.0, 0.5, 0.1]},
            "self_hp": {"norm_rect": [0.0, 0.1, 0.5, 0.1]},
            "self_mp": {"norm_rect": [0.0, 0.2, 0.5, 0.1]},
            "target_frame": {"norm_rect": [0.5, 0.0, 0.5, 0.3]},
            "target_hp": {"norm_rect": [0.5, 0.1, 0.5, 0.1]},
        }
    }
    import json

    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_flags_block_without_danger(tmp_path: Path) -> None:
    out = tmp_path / "blocked.json"
    payload = run_s4_probe(live=True, danger_confirmed=False, out_path=out)
    assert payload["aborted"] == "live_flags_required"
    assert payload["hid_sent"] is False
    assert payload["ok"] is False


def test_cli_without_flags(tmp_path: Path) -> None:
    out = tmp_path / "cli.json"
    code = main(["s4-probe", "--out", str(out)])
    assert code == 2
    text = out.read_text(encoding="utf-8")
    assert "live_flags_required" in text
    assert '"hid_sent": false' in text


def test_self_hp_low_does_not_send_f1(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(clock, poster)
    grabber = ScriptedGrabber([_scene(hp=0.2, target=False)])
    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        grabber=grabber,
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "low.json",
    )
    assert payload["aborted"] == "self_hp_low"
    assert not any(row.action_type == "TargetSelect" for row in backend.log)
    assert payload["hid_sent"] is False


def test_lock_timeout_after_f1(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(clock, poster)
    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        grabber=ScriptedGrabber([_scene(hp=0.95, target=False)]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "timeout.json",
    )
    assert payload["aborted"] == "lock_timeout"
    assert any(row.action_type == "TargetSelect" for row in backend.log)
    assert not any(row.action_type == "SkillActivate" for row in backend.log)
    assert payload["stuck_keys_count"] == 0


def test_closed_loop_f1_lock_f2_drop_escape(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(clock, poster)
    idle = _scene(hp=0.95, target=False)
    locked = _scene(hp=0.95, target=True, target_hp=0.50)
    hurt = _scene(hp=0.95, target=True, target_hp=0.30)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            types = [row.action_type for row in backend.log]
            if "SkillActivate" in types:
                return hurt
            if "TargetSelect" in types:
                return locked
            return idle

    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "ok.json",
    )
    assert payload["ok"] is True
    assert payload["aborted"] is None
    assert payload["target_locked"] is True
    assert payload["target_name_detected"] is True
    assert payload["damage_detected"] is True
    assert abs((payload["initial_target_hp"] or 0) - 0.50) <= 0.03
    assert abs((payload["final_target_hp"] or 0) - 0.30) <= 0.03
    assert payload["f1_to_lock_ms"] is not None
    assert payload["f2_to_hp_drop_ms"] is not None
    assert payload["stuck_keys_count"] == 0
    assert payload["watchdog_tripped"] is False
    types = [row.action_type for row in backend.log]
    assert "TargetSelect" in types
    assert "SkillActivate" in types
    assert types.count("HoldKey") >= 2
    assert any(row.key == "escape" for row in backend.log)
    keys = [c[1] for c in poster.calls if c[0] == "key"]
    assert 0x7A in keys
    assert 0x78 in keys
    assert 0x35 in keys


def test_focus_lost_aborts_before_keys(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=poster,
        focus_probe=lambda: False,
        now_ns=clock,
    )
    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        grabber=ScriptedGrabber([_scene(hp=0.95, target=True, target_hp=0.4)]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        focus_probe=lambda: False,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "focus.json",
    )
    assert payload["aborted"] == "focus_not_parallels"
    assert payload["hid_sent"] is False
    assert poster.calls == []


def test_parser_sees_lock_on_scripted_plate() -> None:
    parsed = HUDParser(_layout()).parse(_scene(hp=0.95, target=True, target_hp=0.4))
    assert parsed.valid
    assert parsed.target_locked is True
    assert (parsed.self_hp_ratio or 0) > 0.8


def test_clean_target_rejects_wounded_lock(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(clock, poster)
    wounded = _scene(hp=0.95, target=True, target_hp=0.44)
    idle = _scene(hp=0.95, target=False)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            types = [row.action_type for row in backend.log]
            if "TargetSelect" in types:
                return wounded
            if any(row.key == "escape" for row in backend.log):
                return idle
            return wounded

    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        clean_target=True,
        grabber=_Aware([wounded]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "wounded.json",
    )
    assert payload["aborted"] == "clean_hp_low"
    assert payload["f2_pulses"] == 0
    assert not any(row.action_type == "SkillActivate" for row in backend.log)


def test_clean_target_double_f2_and_early_damage(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(clock, poster)
    wounded = _scene(hp=0.95, target=True, target_hp=0.44)
    idle = _scene(hp=0.95, target=False)
    fresh = _scene(hp=0.95, target=True, target_hp=0.96)
    hurt = _scene(hp=0.95, target=True, target_hp=0.80)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            types = [row.action_type for row in backend.log]
            if types.count("SkillActivate") >= 2:
                return hurt
            if "TargetSelect" in types:
                return fresh
            if any(row.key == "escape" for row in backend.log):
                return idle
            return wounded

    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        clean_target=True,
        grabber=_Aware([wounded]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "clean.json",
    )
    assert payload["ok"] is True
    assert payload["aborted"] is None
    assert payload["clean_target"] is True
    assert payload["target_locked"] is True
    assert payload["damage_detected"] is True
    assert payload["f2_pulses"] == 2
    assert (payload["initial_target_hp"] or 0) > 0.85
    assert (payload["final_target_hp"] or 1) < (payload["initial_target_hp"] or 0) - 0.05
    assert payload["f2_to_hp_drop_ms"] is not None
    assert payload["session_ms"] < 8000
    assert payload["stuck_keys_count"] == 0
    assert [row.action_type for row in backend.log].count("SkillActivate") == 2
    keys = [c[1] for c in poster.calls if c[0] == "key"]
    assert keys.count(0x78) >= 4
    assert keys.count(0x35) >= 4


def test_engage_any_accepts_wounded_and_records_damage(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(clock, poster)
    wounded = _scene(hp=0.95, target=True, target_hp=0.44)
    hurt = _scene(hp=0.95, target=True, target_hp=0.30)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            if [row.action_type for row in backend.log].count("SkillActivate") >= 2:
                return hurt
            return wounded

    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        engage_any=True,
        grabber=_Aware([wounded]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "engage.json",
    )
    assert payload["ok"] is True
    assert payload["engage_any"] is True
    assert payload["aborted"] is None
    assert abs((payload["initial_target_hp"] or 0) - 0.44) <= 0.03
    assert payload["damage_detected"] is True
    assert payload["f2_pulses"] == 2
    assert payload["f2_to_hp_drop_ms"] is not None
    assert payload["stuck_keys_count"] == 0
    assert not any(row.get("step") == "pre_clear_Escape" for row in payload["steps"])


def test_engage_any_counts_finish_as_damage(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    live = _scene(hp=0.95, target=True, target_hp=0.20)
    dead = _scene(hp=0.95, target=True, target_hp=0.0)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            if any(row.action_type == "SkillActivate" for row in backend.log):
                return dead
            return live

    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        engage_any=True,
        grabber=_Aware([live]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "finish.json",
    )
    assert payload["damage_detected"] is True
    assert payload["final_target_hp"] == 0.0


def test_kill_and_loot_waits_for_death_then_f3(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(clock, poster)
    live = _scene(hp=0.95, target=True, target_hp=0.44)
    hurt = _scene(hp=0.95, target=True, target_hp=0.30)
    dead = _scene(hp=0.95, target=True, target_hp=0.0)
    after_f2 = {"n": 0}

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            skills = [row.action_type for row in backend.log].count("SkillActivate")
            if skills >= 2 and not any(row.key == "F3" for row in backend.log):
                after_f2["n"] += 1
                return dead if after_f2["n"] > 4 else hurt
            return live

    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        kill_and_loot=True,
        grabber=_Aware([live]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "kill.json",
    )
    assert payload["ok"] is True
    assert payload["target_killed"] is True
    assert payload["loot_pickup_sent"] is True
    assert payload["damage_detected"] is True
    assert payload["final_hp"] == 0.0
    assert payload["time_to_kill_ms"] is not None
    assert payload["stuck_keys_count"] == 0
    keys = [row.key for row in backend.log]
    assert keys.count("F2") == 2
    assert "F3" in keys
    steps = [row["step"] for row in payload["steps"]]
    assert steps.index("hp_delta") < steps.index("target_dead")
    assert steps.index("target_dead") < steps.index("F3")
    assert steps.index("F3") < steps.index("Escape")


def test_kill_and_loot_skips_f3_if_mob_lives(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    live = _scene(hp=0.95, target=True, target_hp=0.44)
    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        kill_and_loot=True,
        grabber=ScriptedGrabber([live]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "alive.json",
    )
    assert payload["aborted"] == "kill_timeout"
    assert payload["target_killed"] is False
    assert payload["loot_pickup_sent"] is False
    assert not any(row.key == "F3" for row in backend.log)


def _f2_count(backend: CGEventInputBackend) -> int:
    return sum(1 for row in backend.log if row.action_type == "SkillActivate" and row.key == "F2")


def _f3_count(backend: CGEventInputBackend) -> int:
    return sum(1 for row in backend.log if row.key == "F3")


def test_multi_kill_three_frags_then_stops(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(clock, poster)
    idle = _scene(hp=0.95, target=False)
    live = _scene(hp=0.95, target=True, target_hp=0.90)
    dead = _scene(hp=0.95, target=True, target_hp=0.0)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            last_esc = max(
                (i for i, row in enumerate(backend.log) if row.key == "escape"),
                default=-1,
            )
            last_f1 = max(
                (i for i, row in enumerate(backend.log) if row.action_type == "TargetSelect"),
                default=-1,
            )
            combats = _f2_count(backend) // 2
            loots = _f3_count(backend)
            if combats > loots:
                return dead
            if last_f1 > last_esc:
                return live
            return idle

    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        multi_kill=3,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "multi.json",
    )
    assert payload["ok"] is True
    assert payload["aborted"] is None
    assert payload["farm"] is False
    assert payload["multi_kill"] == 3
    assert payload["kills_completed"] == 3
    assert payload["loot_actions_sent"] == 3
    assert payload["loot_pickup_sent"] is True
    assert payload["stuck_keys_count"] == 0
    assert payload["watchdog_tripped"] is False
    assert payload["total_session_ms"] == payload["session_ms"]
    assert payload["session_ms"] < 45_000
    assert _f2_count(backend) == 6
    assert _f3_count(backend) == 3
    assert not any(row.action_type == "CameraRotate" for row in backend.log)
    frags = [row for row in payload["steps"] if row["step"] == "frag"]
    assert [row["kills_completed"] for row in frags] == [1, 2, 3]


def test_multi_kill_combat_timeout_skips_loot(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    live = _scene(hp=0.95, target=True, target_hp=0.80)
    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        multi_kill=3,
        grabber=ScriptedGrabber([live]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "timeout.json",
    )
    assert payload["kills_completed"] == 0
    assert payload["loot_actions_sent"] == 0
    assert payload["ok"] is False
    assert payload["aborted"] == "session_timeout"
    assert payload["total_session_ms"] >= 44_000
    assert not any(row.key == "F3" for row in backend.log)
    assert any(row.get("step") == "combat_timeout" for row in payload["steps"])


def test_multi_kill_rotates_camera_after_three_f1(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(clock, poster)
    idle = _scene(hp=0.95, target=False)
    live = _scene(hp=0.95, target=True, target_hp=0.90)
    dead = _scene(hp=0.95, target=True, target_hp=0.0)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            rotated = any(row.key == "right_arrow" for row in backend.log)
            if not rotated:
                return idle
            last_esc = max(
                (i for i, row in enumerate(backend.log) if row.key == "escape"),
                default=-1,
            )
            last_f1 = max(
                (i for i, row in enumerate(backend.log) if row.action_type == "TargetSelect"),
                default=-1,
            )
            if _f2_count(backend) >= 2 and _f3_count(backend) == 0:
                return dead
            if last_f1 > last_esc:
                return live
            return idle

    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        multi_kill=1,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "rotate.json",
    )
    assert payload["kills_completed"] == 1
    assert payload["loot_actions_sent"] == 1
    assert any(row.key == "right_arrow" for row in backend.log)
    assert not any(row.action_type == "CameraRotate" for row in backend.log)
    f1_before = 0
    for row in backend.log:
        if row.key == "right_arrow":
            break
        if row.action_type == "TargetSelect":
            f1_before += 1
    assert f1_before == 3
    assert payload["stuck_keys_count"] == 0


def test_multi_kill_caps_at_three(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    idle = _scene(hp=0.95, target=False)
    live = _scene(hp=0.95, target=True, target_hp=0.90)
    dead = _scene(hp=0.95, target=True, target_hp=0.0)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            last_esc = max(
                (i for i, row in enumerate(backend.log) if row.key == "escape"),
                default=-1,
            )
            last_f1 = max(
                (i for i, row in enumerate(backend.log) if row.action_type == "TargetSelect"),
                default=-1,
            )
            if _f2_count(backend) // 2 > _f3_count(backend):
                return dead
            if last_f1 > last_esc:
                return live
            return idle

    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        multi_kill=9,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "cap.json",
    )
    assert payload["multi_kill"] == 3
    assert payload["kills_completed"] == 3
    assert _f3_count(backend) == 3


def test_verify_search_maneuver_then_one_kill(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(clock, poster)
    idle = _scene(hp=0.95, target=False)
    live = _scene(hp=0.95, target=True, target_hp=0.90)
    dead = _scene(hp=0.95, target=True, target_hp=0.0)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            f1 = sum(1 for row in backend.log if row.action_type == "TargetSelect")
            rotated = any(row.key == "right_arrow" for row in backend.log)
            if _f2_count(backend) >= 2 and _f3_count(backend) == 0:
                return dead
            if rotated and f1 >= 2:
                return live
            return idle

    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        verify_search=True,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "search.json",
    )
    assert payload["ok"] is True
    assert payload["aborted"] is None
    assert payload["search_maneuver_executed"] is True
    assert payload["search_maneuver_triggered"] is True
    assert payload["rotation_sent"] is True
    assert payload["walk_step_sent"] is True
    assert payload["target_acquired_after_search"] is True
    assert payload["damage_detected"] is True
    assert payload["target_killed"] is True
    assert payload["loot_pickup_sent"] is True
    assert payload["kills_completed"] == 1
    assert payload["stuck_keys_count"] == 0
    assert payload["watchdog_tripped"] is False
    assert payload["farm"] is False
    assert payload["rotation_type"] == "keyboard_arrow"
    assert any(row.key == "right_arrow" and row.hold_duration_ms == 450 for row in backend.log)
    assert not any(row.action_type == "CameraRotate" for row in backend.log)
    assert not any(c[0] == "mouse" for c in poster.calls)
    downs = [row for row in backend.log if row.action_type == "HoldKey" and row.key == "w" and row.hold_duration_ms == 500]
    assert downs
    keys = [c[1] for c in poster.calls if c[0] == "key"]
    assert 0x0D in keys
    assert 0x7C in keys
    steps = [row["step"] for row in payload["steps"]]
    assert steps.index("search_maneuver_triggered") < steps.index("right_arrow")
    assert steps.index("right_arrow") < steps.index("HoldKey")
    assert steps.index("HoldKey") < steps.index("locked")
    assert steps.index("locked") < steps.index("F2")
    assert steps.index("F3") < steps.index("Escape")
    assert sum(1 for row in backend.log if row.action_type == "TargetSelect") == 2
    assert _f2_count(backend) == 2
    assert _f3_count(backend) == 1


def test_verify_search_arrow_then_combat_if_first_f1_locks(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(clock, poster)
    live = _scene(hp=0.95, target=True, target_hp=0.80)
    dead = _scene(hp=0.95, target=True, target_hp=0.0)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            if _f2_count(backend) >= 2:
                return dead
            return live

    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        verify_search=True,
        grabber=_Aware([live]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "not_empty.json",
    )
    assert payload["ok"] is True
    assert payload["rotation_sent"] is True
    assert payload["rotation_type"] == "keyboard_arrow"
    assert payload["target_acquired_after_search"] is False
    assert payload["walk_step_sent"] is False
    assert payload["target_killed"] is True
    assert payload["loot_pickup_sent"] is True
    assert any(row.key == "right_arrow" for row in backend.log)
    assert not any(row.action_type == "CameraRotate" for row in backend.log)
    assert not any(c[0] == "mouse" for c in poster.calls)
    assert 0x7C in [c[1] for c in poster.calls if c[0] == "key"]


def test_verify_search_no_target_after_maneuver(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    idle = _scene(hp=0.95, target=False)
    payload = run_s4_probe(
        live=True,
        danger_confirmed=True,
        verify_search=True,
        grabber=ScriptedGrabber([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "empty.json",
    )
    assert payload["aborted"] == "search_no_target"
    assert payload["search_maneuver_executed"] is True
    assert payload["rotation_sent"] is True
    assert payload["walk_step_sent"] is True
    assert payload["target_acquired_after_search"] is False
    assert payload["target_killed"] is False
    assert payload["loot_pickup_sent"] is False
    assert payload["watchdog_tripped"] is False
    assert payload["stuck_keys_count"] == 0
    assert payload["rotation_type"] == "keyboard_arrow"
    assert not any(row.key == "F2" for row in backend.log)
    assert not any(row.action_type == "CameraRotate" for row in backend.log)
    assert sum(1 for row in backend.log if row.key == "right_arrow" and row.hold_duration_ms == 450) == 3
