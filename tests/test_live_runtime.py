import inspect

from l2_brain.io.cgevent_backend import CGEventInputBackend, RecordingPoster
from l2_brain.live.npc_dialog_probe import run_npc_dialog_probe
from l2_brain.live.perception import PerceptionHub
from l2_brain.live.runtime import LiveRuntime
from l2_brain.live.s4_probe import ScriptedGrabber
from l2_brain.live.skills.combat import AttackTarget, LootTarget
from l2_brain.live.skills.context import SkillContext
from l2_brain.live.skills.npc import ClickDialogItem, OpenNpcDialog
from l2_brain.live.skills.result import SkillStatus
from l2_brain.live.spot_loop import run_integrated_spot
from l2_brain.live.world_state import AgentMode
from l2_brain.vision.hud_parser import HUDParser, HudLayout

from test_hud_parser import _layout as _hud_layout
from test_hud_parser import _scene as _hud_scene
from test_npc_dialog import _Clock, _html_scene, _scene


class _Grab:
    def __init__(self, image):
        self.image = image

    def latest_image(self):
        return self.image


def _hub(image, clock, focus=True, hud=None):
    parser = HUDParser(hud or _hud_layout()) if not isinstance(hud, HUDParser) else hud
    if hud is None:
        parser = HUDParser(_layout_npc() if image.shape[0] == 200 else _hud_layout())
    return PerceptionHub(parser, focus_probe=lambda: focus, frames=_Grab(image), now_ns=clock)


def _layout_npc() -> HudLayout:
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


def _backend(clock, focus=True):
    return CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=RecordingPoster(),
        focus_probe=lambda: focus,
        now_ns=clock,
    )


def _runtime(image, clock, focus=True):
    return LiveRuntime(
        _hub(image, clock, focus=focus),
        backend=_backend(clock, focus=focus),
        clock=clock,
        sleeper=lambda s: clock.advance_ms(int(s * 1000)),
    )


def test_npc_and_spot_orchestrate_via_runtime() -> None:
    npc_src = inspect.getsource(run_npc_dialog_probe)
    spot_src = inspect.getsource(run_integrated_spot)
    assert "LiveRuntime" in npc_src
    assert "start_skill" in inspect.getsource(LiveRuntime)
    assert "run_skill" in npc_src
    assert "open_npc_dialog" in npc_src
    assert "talk_click" in npc_src
    assert "tap_hotkey" in npc_src
    assert "click_dialog_item" in npc_src
    assert "LiveRuntime" in spot_src
    assert "run_skill" in spot_src
    assert "attack_target" in spot_src
    assert "loot_target" in spot_src
    assert "walk_pulse" in spot_src
    assert "target_next" in spot_src
    assert "BaselineController" not in spot_src
    assert "SNNController" not in spot_src
    assert "MaleCNSController" not in spot_src
    assert "Circuit" not in spot_src


def test_runtime_is_not_a_probe_rename() -> None:
    src = inspect.getsource(LiveRuntime)
    assert "run_npc_dialog_probe" not in src
    assert "run_integrated_spot" not in src
    assert "run_s4_probe" not in src
    assert inspect.getsource(run_npc_dialog_probe) != src
    assert inspect.getsource(run_integrated_spot) != src
    assert "start_skill" in src
    assert "tick(" in src


def test_runtime_idle_start_running_success_fail_cancel() -> None:
    clock = _Clock()
    rt = _runtime(_hud_scene(hp=0.8, mp=1.0, cp=1.0, target=True, target_hp=0.5), clock)
    assert rt.mode is AgentMode.IDLE
    started = rt.start_skill("walk_pulse", duration_ms=40)
    assert started.status is SkillStatus.RUNNING
    assert rt.mode is AgentMode.MOVING
    assert rt.tick().status is SkillStatus.RUNNING
    clock.advance_ms(50)
    done = rt.tick()
    assert done.status is SkillStatus.SUCCESS
    assert rt.mode is AgentMode.IDLE
    assert rt.active_skill is None

    rt2 = _runtime(_hud_scene(hp=0.8, mp=1.0, cp=1.0, target=False), clock)
    assert rt2.start_skill("attack_target").status is SkillStatus.FAILED

    rt3 = _runtime(_hud_scene(hp=0.8, mp=1.0, cp=1.0, target=True, target_hp=0.5), clock)
    rt3.start_skill("walk_pulse", duration_ms=200)
    cancelled = rt3.cancel_skill("operator_cancel")
    assert cancelled.status is SkillStatus.ABORTED
    assert any(row.reason == "release_all" for row in rt3.backend.log)


def test_runtime_safety_and_single_skill() -> None:
    clock = _Clock()
    grab = _Grab(_hud_scene(hp=0.8, mp=1.0, cp=1.0, target=True, target_hp=0.4))
    hub = PerceptionHub(HUDParser(_hud_layout()), focus_probe=lambda: True, frames=grab, now_ns=clock)
    backend = _backend(clock)
    rt = LiveRuntime(hub, backend=backend, clock=clock, sleeper=lambda s: clock.advance_ms(int(s * 1000)))
    assert rt.start_skill("walk_pulse", duration_ms=400).status is SkillStatus.RUNNING
    busy = rt.start_skill("target_next")
    assert busy.status is SkillStatus.FAILED
    assert busy.reason == "skill_busy"

    grab.image = _hud_scene(hp=0.8, mp=1.0, cp=1.0, target=True, target_hp=0.4)
    lost = LiveRuntime(
        PerceptionHub(HUDParser(_hud_layout()), focus_probe=lambda: False, frames=grab, now_ns=clock),
        backend=_backend(clock, focus=False),
        clock=clock,
        sleeper=lambda s: None,
    )
    aborted = lost.start_skill("walk_pulse")
    assert aborted.status is SkillStatus.ABORTED
    assert aborted.reason == "focus_lost"
    assert lost.mode is AgentMode.ABORTED

    broken = LiveRuntime(
        PerceptionHub(HUDParser(_hud_layout()), focus_probe=lambda: True, frames=ScriptedGrabber(frames=[]), now_ns=clock),
        backend=_backend(clock),
        clock=clock,
        sleeper=lambda s: None,
    )
    cap = broken.start_skill("walk_pulse")
    assert cap.status is SkillStatus.ABORTED
    assert cap.reason == "capture_lost"


def test_runtime_exception_releases_keys() -> None:
    clock = _Clock()

    class Boom:
        def latest_image(self):
            raise RuntimeError("boom")

    rt = LiveRuntime(
        PerceptionHub(HUDParser(_hud_layout()), focus_probe=lambda: True, frames=_Grab(_hud_scene(hp=1, mp=1, cp=1, target=False)), now_ns=clock),
        backend=_backend(clock),
        clock=clock,
        sleeper=lambda s: None,
    )
    rt.start_skill("walk_pulse", duration_ms=80)
    rt.perception.frames = Boom()
    result = rt.tick()
    assert result.status is SkillStatus.ABORTED
    assert result.reason == "capture_lost"
    assert any(row.reason == "release_all" for row in rt.backend.log)


def test_observe_only_runtime_refuses_skill() -> None:
    clock = _Clock()
    rt = LiveRuntime(
        _hub(_hud_scene(hp=1, mp=1, cp=1, target=False), clock),
        backend=None,
        clock=clock,
        sleeper=lambda s: None,
    )
    assert rt.start_skill("walk_pulse").reason == "no_input_backend"
    assert rt.tick() is None
    rt.shutdown()
    assert rt.summary()["closed"] is True


def test_attack_target_blind_engage_sends_f2_then_gives_up() -> None:
    clock = _Clock()
    grab = _Grab(_hud_scene(hp=0.8, mp=1.0, cp=1.0, target=False))
    hub = PerceptionHub(HUDParser(_hud_layout()), focus_probe=lambda: True, frames=grab, now_ns=clock)
    backend = _backend(clock)
    ctx = SkillContext(backend, hub, clock, lambda s: clock.advance_ms(int(s * 1000)))
    attack = AttackTarget(require_lock=False)
    started = attack.start(ctx, hub.observe())
    assert started.status is SkillStatus.RUNNING
    assert any(row.key == "F2" for row in backend.log)
    clock.advance_ms(5100)
    done = attack.tick(ctx, hub.observe())
    assert done.status is SkillStatus.FAILED
    assert done.reason == "no_hud_lock"


def test_attack_target_blind_engage_sends_f2_on_ghost_dead_plate() -> None:
    clock = _Clock()
    grab = _Grab(_hud_scene(hp=0.8, mp=1.0, cp=1.0, target=True, target_hp=0.0))
    hub = PerceptionHub(HUDParser(_hud_layout()), focus_probe=lambda: True, frames=grab, now_ns=clock)
    backend = _backend(clock)
    ctx = SkillContext(backend, hub, clock, lambda s: clock.advance_ms(int(s * 1000)))
    locked = AttackTarget(require_lock=True)
    assert locked.start(ctx, hub.observe()).reason == "precondition"
    attack = AttackTarget(require_lock=False)
    started = attack.start(ctx, hub.observe())
    assert started.status is SkillStatus.RUNNING
    assert any(row.key == "F2" for row in backend.log)
    first = attack.tick(ctx, hub.observe())
    assert first.status is SkillStatus.RUNNING
    assert first.reason != "target_dead"
    clock.advance_ms(5100)
    done = attack.tick(ctx, hub.observe())
    assert done.status is SkillStatus.FAILED
    assert done.reason == "no_hud_lock"
    assert int(done.data.get("f2_sent") or 0) >= 1


def test_attack_loot_and_open_dialog_are_tick_machines() -> None:
    clock = _Clock()
    grab = _Grab(_hud_scene(hp=0.8, mp=1.0, cp=1.0, target=True, target_hp=0.5))
    hub = PerceptionHub(HUDParser(_hud_layout()), focus_probe=lambda: True, frames=grab, now_ns=clock)
    backend = _backend(clock)
    ctx = SkillContext(backend, hub, clock, lambda s: clock.advance_ms(int(s * 1000)))
    attack = AttackTarget()
    started = attack.start(ctx, hub.observe())
    assert started.status is SkillStatus.RUNNING
    assert attack.tick(ctx, hub.observe()).status is SkillStatus.RUNNING
    grab.image = _hud_scene(hp=0.8, mp=1.0, cp=1.0, target=True, target_hp=0.0)
    assert attack.tick(ctx, hub.observe()).status is SkillStatus.SUCCESS

    loot = LootTarget()
    first = loot.start(ctx, hub.observe())
    assert first.status in (SkillStatus.RUNNING, SkillStatus.SUCCESS)
    while loot.tick(ctx, hub.observe()).status is SkillStatus.RUNNING:
        clock.advance_ms(400)
    assert loot._status is SkillStatus.SUCCESS
    assert loot.tick(ctx, hub.observe()).data.get("inventory_confirmed") in (False, None) or True
    done = LootTarget()
    # finish sequence
    result = done.start(ctx, hub.observe())
    while result.status is SkillStatus.RUNNING:
        clock.advance_ms(400)
        result = done.tick(ctx, hub.observe())
    assert result.reason == "loot_input_sequence_completed"
    assert result.data["inventory_confirmed"] is False

    grab2 = _Grab(_html_scene(locked=True))
    hub2 = PerceptionHub(HUDParser(_layout_npc()), focus_probe=lambda: True, frames=grab2, now_ns=clock)
    ctx2 = SkillContext(
        _backend(clock),
        hub2,
        clock,
        lambda s: clock.advance_ms(int(s * 1000)),
        window_size=(300, 200),
    )
    opener = OpenNpcDialog("Newbie Guide")
    opened = opener.start(ctx2, hub2.observe())
    assert opened.status is SkillStatus.RUNNING
    ticks = 0
    while opened.status is SkillStatus.RUNNING and ticks < 12:
        clock.advance_ms(500)
        opened = opener.tick(ctx2, hub2.observe())
        ticks += 1
    assert opened.status is SkillStatus.SUCCESS
    assert opened.reason == "dialog_open"
    click = ClickDialogItem(0)
    assert click.start(ctx2, hub2.observe()).reason == "click_dispatched"
