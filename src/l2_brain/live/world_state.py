"""Aggregated live observation. Not a quest planner. Not sim GT."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentMode(Enum):
    """What the agent is doing. Not a fact of the pixels."""

    IDLE = "idle"
    MOVING = "moving"
    COMBAT = "combat"
    NPC_INTERACTION = "npc_interaction"
    RECOVERY = "recovery"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class WorldState:
    timestamp_ns: int
    capture_ok: bool
    focus_ok: bool
    self_hp: float | None
    self_cp: float | None
    self_mp: float | None
    target_locked: bool | None
    target_hp: float | None
    target_dead: bool | None
    dialog_open: bool | None
    dialog_items: tuple[tuple[int, int], ...]
    ui_modal_open: bool | None
    motion_magnitude: float | None
    last_error: str | None
    frame_width: int | None = None
    frame_height: int | None = None
    hud_valid: bool | None = None


def empty_world_state(*, timestamp_ns: int, last_error: str | None = None) -> WorldState:
    return WorldState(
        timestamp_ns=timestamp_ns,
        capture_ok=False,
        focus_ok=False,
        self_hp=None,
        self_cp=None,
        self_mp=None,
        target_locked=None,
        target_hp=None,
        target_dead=None,
        dialog_open=None,
        dialog_items=(),
        ui_modal_open=None,
        motion_magnitude=None,
        last_error=last_error,
        frame_width=None,
        frame_height=None,
        hud_valid=None,
    )
