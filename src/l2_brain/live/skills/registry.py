from __future__ import annotations

from collections.abc import Callable

from l2_brain.live.skills.base import Skill
from l2_brain.live.skills.combat import AttackTarget, LootTarget
from l2_brain.live.skills.movement import RotateLeft, RotateRight, UTurn, WalkPulse
from l2_brain.live.skills.npc import ApproachNamedNpc, ClickDialogItem, OpenNpcDialog, TalkClick
from l2_brain.live.skills.targeting import TargetByName, TargetNext
from l2_brain.live.skills.ui import CloseDialog, TapHotkey

Factory = Callable[..., Skill]


class SkillRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Factory] = {}

    def register(self, name: str, factory: Factory) -> None:
        self._factories[name] = factory

    def get(self, name: str, **kwargs: object) -> Skill:
        factory = self._factories.get(name)
        if factory is None:
            raise KeyError(f"unknown skill {name!r}")
        return factory(**kwargs)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


def default_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register("walk_pulse", WalkPulse)
    registry.register("rotate_left", RotateLeft)
    registry.register("rotate_right", RotateRight)
    registry.register("u_turn", UTurn)
    registry.register("target_next", TargetNext)
    registry.register("target_by_name", TargetByName)
    registry.register("close_dialog", CloseDialog)
    registry.register("attack_target", AttackTarget)
    registry.register("loot_target", LootTarget)
    registry.register("approach_named_npc", ApproachNamedNpc)
    registry.register("open_npc_dialog", OpenNpcDialog)
    registry.register("click_dialog_item", ClickDialogItem)
    registry.register("talk_click", TalkClick)
    registry.register("tap_hotkey", TapHotkey)
    return registry
