from pathlib import Path

import numpy as np

from l2_brain.cli import main
from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster
from l2_brain.live.s4_probe import ScriptedGrabber
from l2_brain.live.spot_loop import (
    KILL_CAP,
    PEEL_MS,
    UTURN_WALK_MS,
    WALK_MS,
    run_integrated_spot,
    should_aggro_interrupt,
    should_l1_unjam,
)
from l2_brain.vision.hud_parser import HUDParser, HudLayout


class _Clock:
    def __init__(self) -> None:
        self.t = 10**12

    def __call__(self) -> int:
        return self.t

    def advance_ms(self, ms: int) -> None:
        self.t += ms * 1_000_000


def _write_profile(path: Path) -> Path:
    HUDParser(
        HudLayout.from_mapping(
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
    )
    import json

    path.write_text(
        json.dumps(
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
        ),
        encoding="utf-8",
    )
    return path


def _scene(*, hp: float, target: bool, target_hp: float = 1.0) -> np.ndarray:
    image = np.full((100, 200, 3), 18, dtype=np.uint8)
    image[0:10, 0 : int(100 * 0.95)] = (220, 180, 20)
    image[10:20, 0 : int(100 * hp)] = (220, 20, 20)
    image[20:30, 0:100] = (20, 40, 220)
    if target:
        image[0:30, 100:200] = (40, 32, 28)
        image[10:20, 100 : 100 + int(100 * target_hp)] = (220, 20, 20)
    return image


def _backend(clock: _Clock, poster: RecordingPoster | None = None) -> CGEventInputBackend:
    return CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=poster or RecordingPoster(),
        focus_probe=lambda: True,
        now_ns=clock,
    )


def _f2(backend: CGEventInputBackend) -> int:
    return sum(1 for row in backend.log if row.action_type == "SkillActivate" and row.key == "F2")


def _f3(backend: CGEventInputBackend) -> int:
    return sum(1 for row in backend.log if row.key == "F3")


def test_flags_required(tmp_path: Path) -> None:
    payload = run_integrated_spot(live=True, danger_confirmed=False, out_path=tmp_path / "x.json")
    assert payload["aborted"] == "live_flags_required"
    assert payload["hid_sent"] is False
    assert payload["farm"] is False


def test_cli_without_flags(tmp_path: Path) -> None:
    out = tmp_path / "cli.json"
    code = main(["s4-integrated-spot", "--kills", "10", "--no-timeout", "--no-heal", "--out", str(out)])
    assert code == 2
    assert "live_flags_required" in out.read_text(encoding="utf-8")


def test_five_frags_then_stops(tmp_path: Path) -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(clock, poster)
    idle = _scene(hp=0.95, target=False)
    live = _scene(hp=0.95, target=True, target_hp=0.90)
    dead = _scene(hp=0.95, target=True, target_hp=0.0)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
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
        kills=5,
        timeout_s=None,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "five.json",
    )
    assert payload["ok"] is True
    assert payload["aborted"] is None
    assert payload["farm"] is False
    assert payload["timeout_s"] is None
    assert payload["total_kills"] == 5
    assert payload["kills_completed"] == 5
    assert len(payload["frags"]) == 5
    assert _f3(backend) == 15
    assert payload["stuck_keys_count"] == 0
    assert payload["heal_sent"] is False
    assert payload["l1_triggers"] == 0
    assert not any(row.key == "F4" for row in backend.log)
    assert payload["encode"]["n"] >= 1
    w_holds = [row.hold_duration_ms for row in backend.log if row.key == "w" and row.hold_duration_ms]
    assert all(int(ms) <= 800 for ms in w_holds)


def test_ten_frags_then_stops(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    idle = _scene(hp=0.95, target=False)
    live = _scene(hp=0.95, target=True, target_hp=0.90)
    dead = _scene(hp=0.95, target=True, target_hp=0.0)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
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
        kills=10,
        timeout_s=None,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "ten.json",
    )
    assert payload["ok"] is True
    assert payload["total_kills"] == 10
    assert payload["total_time_sec"] > 0
    assert payload["avg_combat_sec"] is not None
    assert payload["u_turns"] == 0
    assert payload["aggro_triggers"] == 0
    assert payload["stuck_keys"] == 0
    assert payload["farm"] is False
    assert _f3(backend) == 30


def test_roam_then_lock(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    idle = _scene(hp=0.95, target=False)
    live = _scene(hp=0.95, target=True, target_hp=0.80)
    dead = _scene(hp=0.95, target=True, target_hp=0.0)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            last_walk = max(
                (i for i, row in enumerate(backend.log) if row.key == "w" and row.hold_duration_ms == WALK_MS),
                default=-1,
            )
            last_f1 = max(
                (i for i, row in enumerate(backend.log) if row.action_type == "TargetSelect"),
                default=-1,
            )
            if last_walk < 0 or last_f1 <= last_walk:
                return idle
            f2_after = sum(1 for i, row in enumerate(backend.log) if i > last_f1 and row.key == "F2")
            if f2_after >= 2:
                return dead
            return live

    payload = run_integrated_spot(
        live=True,
        danger_confirmed=True,
        kills=1,
        timeout_s=None,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "roam.json",
    )
    assert payload["kills_completed"] == 1
    assert payload["roam_cycles"] >= 1
    assert payload["u_turns"] == 0
    assert payload["frags"][0]["search_ms"] > 1000
    assert payload["frags"][0]["roam_cycles"] >= 1
    assert any(row.key == "right_arrow" for row in backend.log)
    assert any(row.key == "w" and row.hold_duration_ms == WALK_MS for row in backend.log)


def test_blind_melee_counts_kill_when_self_hp_drops(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    idle = _scene(hp=0.95, target=False)
    hurt = _scene(hp=0.70, target=False)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            if _f2(backend) >= 1:
                return hurt
            return idle

    payload = run_integrated_spot(
        live=True,
        danger_confirmed=True,
        kills=1,
        timeout_s=None,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "melee.json",
    )
    assert payload["kills_completed"] == 1
    assert payload["attack_skill_success"] >= 1
    assert any(row.get("via") == "blind_melee" for row in payload["steps"])
    assert _f3(backend) >= 3
    assert any(row.key == "F2" for row in backend.log)


def test_roam_limit(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    idle = _scene(hp=0.95, target=False)
    payload = run_integrated_spot(
        live=True,
        danger_confirmed=True,
        kills=1,
        timeout_s=None,
        grabber=ScriptedGrabber([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "limit.json",
    )
    assert payload["aborted"] == "roam_limit"
    assert payload["kills_completed"] == 0
    assert payload["roam_cycles"] == 15
    assert payload["u_turns_executed"] == 5
    assert any(row.get("step") == "u_turn" for row in payload["steps"])
    assert any(row.key == "w" and row.hold_duration_ms == UTURN_WALK_MS for row in backend.log)
    assert any(row.get("step") == "blind_engage" for row in payload["steps"])
    assert any(row.key == "F2" for row in backend.log)
    assert _f3(backend) >= 3
    assert payload["loot_pickup_sent"] is True
    assert any(row.get("via") == "after_f2" for row in payload["steps"])


def test_blind_f2_loots_without_kill_credit(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    idle = _scene(hp=0.95, target=False)
    payload = run_integrated_spot(
        live=True,
        danger_confirmed=True,
        kills=1,
        timeout_s=20.0,
        grabber=ScriptedGrabber([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "loot-no-kill.json",
    )
    assert payload["kills_completed"] == 0
    assert _f3(backend) >= 3
    assert payload["loot_pickup_sent"] is True
    assert any(row.get("via") == "after_f2" for row in payload["steps"])
    assert not any(row.get("via") == "blind_melee" for row in payload["steps"])


def test_l1_not_on_grass_short_combat(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    live = _scene(hp=0.95, target=True, target_hp=0.80)
    dead = _scene(hp=0.95, target=True, target_hp=0.0)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            if _f2(backend) >= 2:
                return dead
            return live

    payload = run_integrated_spot(
        live=True,
        danger_confirmed=True,
        kills=1,
        timeout_s=None,
        grabber=_Aware([live]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "grass.json",
    )
    assert payload["kills_completed"] == 1
    assert payload["l1_triggers"] == 0
    assert not any(row.get("step") == "l1_peel" for row in payload["steps"])
    assert not any(row.get("step") == "l1_slide" for row in payload["steps"])


def test_l1_peel_only_after_static_f2(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    live = _scene(hp=0.95, target=True, target_hp=0.80)
    dead = _scene(hp=0.95, target=True, target_hp=0.0)

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            peeled = any(
                row.key in ("right_arrow", "left_arrow") and row.hold_duration_ms == PEEL_MS
                for row in backend.log
            )
            if peeled and _f2(backend) >= 2:
                return dead
            return live

    payload = run_integrated_spot(
        live=True,
        danger_confirmed=True,
        kills=1,
        timeout_s=None,
        grabber=_Aware([live]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "l1.json",
    )
    assert payload["l1_triggers"] >= 1
    assert any(row.get("step") == "l1_peel" for row in payload["steps"])
    assert not any(row.get("step") == "l1_slide" for row in payload["steps"])
    assert not any(row.key == "w" for row in backend.log)
    assert any(row.key in ("right_arrow", "left_arrow") and row.hold_duration_ms == PEEL_MS for row in backend.log)
    assert payload["stuck_keys_count"] == 0


def test_aggro_interrupt_retargets(tmp_path: Path) -> None:
    clock = _Clock()
    backend = _backend(clock)
    idle = _scene(hp=0.95, target=False)
    live = _scene(hp=0.95, target=True, target_hp=0.90)
    hurt = _scene(hp=0.70, target=True, target_hp=0.90)
    dead = _scene(hp=0.70, target=True, target_hp=0.0)
    first_f2_t: int | None = None

    class _Aware(ScriptedGrabber):
        def latest_image(self) -> np.ndarray:
            nonlocal first_f2_t
            if _f2(backend) >= 2 and first_f2_t is None:
                first_f2_t = clock.t
            esc_after = any(
                i
                for i, row in enumerate(backend.log)
                if row.key == "escape" and first_f2_t is not None
            )
            if first_f2_t is not None and esc_after and _f2(backend) >= 4:
                return dead
            if first_f2_t is not None and clock.t - first_f2_t >= 2_600_000_000:
                return hurt
            last_esc = max((i for i, row in enumerate(backend.log) if row.key == "escape"), default=-1)
            last_f1 = max(
                (i for i, row in enumerate(backend.log) if row.action_type == "TargetSelect"),
                default=-1,
            )
            if last_f1 > last_esc:
                return live
            return idle

    payload = run_integrated_spot(
        live=True,
        danger_confirmed=True,
        kills=1,
        timeout_s=None,
        grabber=_Aware([idle]),
        backend=backend,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
        now_ns=clock,
        profile_path=_write_profile(tmp_path / "hud.json"),
        out_path=tmp_path / "aggro.json",
    )
    assert payload["aggro_triggers"] >= 1
    assert any(row.get("step") == "aggro_lock" for row in payload["steps"])
    assert any(row.key == "escape" for row in backend.log)
    assert payload["kills_completed"] == 1


def test_rules() -> None:
    hist = [0.90, 0.90, 0.90, 0.90, 0.90]
    assert should_aggro_interrupt(
        self_hp=0.80, prev_self_hps=hist, target_locked=False, target_no_damage_s=0.0
    )
    assert not should_aggro_interrupt(
        self_hp=0.89, prev_self_hps=hist, target_locked=False, target_no_damage_s=0.0
    )
    assert should_aggro_interrupt(
        self_hp=0.885, prev_self_hps=hist, target_locked=False, target_no_damage_s=0.0
    )
    assert should_aggro_interrupt(
        self_hp=0.80, prev_self_hps=hist, target_locked=True, target_no_damage_s=2.6
    )
    assert not should_aggro_interrupt(
        self_hp=0.80, prev_self_hps=hist, target_locked=True, target_no_damage_s=1.0
    )
    assert not should_l1_unjam(f2_active_s=3.1, target_damaged=False, static_ticks=5)
    assert should_l1_unjam(f2_active_s=3.1, target_damaged=False, static_ticks=6)
    assert not should_l1_unjam(f2_active_s=2.9, target_damaged=False, static_ticks=6)
    assert not should_l1_unjam(f2_active_s=4.0, target_damaged=True, static_ticks=6)


def test_kill_cap_is_ten() -> None:
    assert KILL_CAP == 10
