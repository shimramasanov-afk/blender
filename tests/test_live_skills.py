from dataclasses import replace

from l2_brain.io.chat_commander import target_by_name as real_target_by_name
from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster
from l2_brain.live.perception import PerceptionHub
from l2_brain.live.s4_probe import SEARCH_HOLD_MAX_MS, ScriptedGrabber
from l2_brain.live.skills.context import SkillContext
from l2_brain.live.skills.movement import WalkPulse
from l2_brain.live.skills.registry import default_registry
from l2_brain.live.skills.result import SkillStatus
from l2_brain.live.skills.targeting import CHAT_LOCK_WAIT_S, TargetByName, TargetNext
from l2_brain.live.skills.ui import CloseDialog
from l2_brain.live.world_state import empty_world_state
from l2_brain.vision.hud_parser import HUDParser, HudLayout

from test_npc_dialog import _Clock, _html_scene, _scene


def _layout() -> HudLayout:
    return HudLayout.from_mapping(
        {
            "hud": {
                "self_bars": {"norm_rect": [0.0, 0.0, 0.4, 0.18]},
                "self_cp": {"norm_rect": [0.0, 0.0, 0.4, 0.06]},
                "self_hp": {"norm_rect": [0.0, 0.06, 0.4, 0.06]},
                "self_mp": {"norm_rect": [0.0, 0.12, 0.4, 0.06]},
                "target_frame": {"norm_rect": [0.5, 0.0, 0.5, 0.18]},
                "target_hp": {"norm_rect": [0.5, 0.06, 0.5, 0.06]},
            }
        }
    )


def _ctx(frames, *, focus=True, clock=None):
    clock = clock or _Clock()
    backend = CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=RecordingPoster(),
        focus_probe=lambda: focus,
        now_ns=clock,
    )
    hub = PerceptionHub(HUDParser(_layout()), focus_probe=lambda: focus, frames=frames, now_ns=clock)
    return SkillContext(
        input_backend=backend,
        perception=hub,
        clock=clock,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
    ), clock, backend


def test_walk_pulse_success_failed_aborted() -> None:
    frames = ScriptedGrabber(frames=[_scene(locked=False)])
    ctx, clock, backend = _ctx(frames)
    state = ctx.perception.observe()
    skill = WalkPulse(duration_ms=40)
    started = skill.start(ctx, state)
    assert started.status is SkillStatus.RUNNING
    still = skill.tick(ctx, state)
    assert still.status is SkillStatus.RUNNING
    clock.advance_ms(50)
    done = skill.tick(ctx, ctx.perception.observe())
    assert done.status is SkillStatus.SUCCESS
    assert done.reason == "pulse_complete"
    keys = [row.key for row in backend.log if row.key == "w"]
    assert keys[0] == "w"
    assert any(row.action_type == "HoldKey" or row.key == "w" for row in backend.log)

    skill2 = WalkPulse(duration_ms=40)
    ctx2, clock2, backend2 = _ctx(frames, focus=False, clock=_Clock())
    failed = skill2.start(ctx2, ctx2.perception.observe())
    assert failed.status is SkillStatus.FAILED
    assert failed.reason == "precondition"

    ctx3, clock3, backend3 = _ctx(ScriptedGrabber(frames=[_scene(locked=False)]))
    skill3 = WalkPulse(duration_ms=80)
    skill3.start(ctx3, ctx3.perception.observe())
    aborted = skill3.cancel(ctx3, "operator")
    assert aborted.status is SkillStatus.ABORTED
    assert any(row.reason == "release_all" for row in backend3.log)


def test_walk_pulse_never_exceeds_hold_cap() -> None:
    skill = WalkPulse(duration_ms=10_000)
    assert skill._duration_ms <= SEARCH_HOLD_MAX_MS


def test_target_next_success_and_fail() -> None:
    locked = ScriptedGrabber(frames=[_scene(locked=True)])
    ctx, clock, _backend = _ctx(locked)
    skill = TargetNext(wait_s=0.2)
    started = skill.start(ctx, ctx.perception.observe())
    assert started.status is SkillStatus.SUCCESS

    empty = ScriptedGrabber(frames=[_scene(locked=False)])
    ctx2, clock2, _b = _ctx(empty)
    skill2 = TargetNext(wait_s=0.05)
    assert skill2.start(ctx2, ctx2.perception.observe()).status is SkillStatus.RUNNING
    clock2.advance_ms(80)
    assert skill2.tick(ctx2, ctx2.perception.observe()).status is SkillStatus.FAILED


def test_target_by_name_uses_chat_commander() -> None:
    from l2_brain.live.skills import targeting as targeting_mod

    assert targeting_mod.target_by_name is real_target_by_name
    frames = ScriptedGrabber(frames=[_scene(locked=True)])
    ctx, clock, backend = _ctx(frames)
    skill = TargetByName("Newbie Guide")
    result = skill.start(ctx, ctx.perception.observe())
    assert result.status is SkillStatus.SUCCESS
    assert any(row.reason == "type_text" and row.key == "/" for row in backend.log)


def test_target_by_name_lock_probe_uses_world_reader_after_capture_gap() -> None:
    frames = ScriptedGrabber(frames=[_scene(locked=False)])
    ctx, clock, backend = _ctx(frames)
    hits = {"n": 0}

    def world_reader():
        hits["n"] += 1
        if hits["n"] == 1:
            return empty_world_state(timestamp_ns=clock(), last_error="capture_lost")
        locked = ctx.perception.observe()
        return replace(locked, capture_ok=True, focus_ok=True, target_locked=True)

    ctx.world_reader = world_reader
    skill = TargetByName("Newbie Guide")
    result = skill.start(ctx, ctx.perception.observe())
    assert result.status is SkillStatus.SUCCESS
    assert hits["n"] >= 2
    assert int(ctx.log.get("lock_probe_capture_ok") or 0) >= 1
    assert CHAT_LOCK_WAIT_S >= 2.0


def test_close_dialog_and_registry() -> None:
    frames = ScriptedGrabber(frames=[_html_scene(locked=True), _scene(locked=True)])
    ctx, clock, backend = _ctx(frames)
    open_state = ctx.perception.observe()
    assert open_state.dialog_open is True
    skill = CloseDialog()
    assert skill.start(ctx, open_state).status is SkillStatus.RUNNING
    closed = ctx.perception.observe()
    assert skill.tick(ctx, closed).status is SkillStatus.SUCCESS
    names = default_registry().names()
    assert "walk_pulse" in names
    assert "target_by_name" in names
    assert "attack_target" in names
    assert "open_npc_dialog" in names
    assert "talk_click" in names
    assert "tap_hotkey" in names
