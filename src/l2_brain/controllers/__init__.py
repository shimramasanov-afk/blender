from __future__ import annotations

from l2_brain.controllers.base import Controller
from l2_brain.controllers.reactive import ReactiveController
from l2_brain.controllers.recurrent import RecurrentController
from l2_brain.controllers.snn import SpikingController

REGISTRY: dict[str, type] = {
    "reactive": ReactiveController,
    "recurrent": RecurrentController,
    "snn": SpikingController,
}


def make_controller(name: str) -> Controller:
    try:
        cls = REGISTRY[name]
    except KeyError as exc:
        known = ", ".join(sorted(REGISTRY))
        raise ValueError(f"unknown controller {name!r}; known: {known}") from exc
    return cls()


__all__ = [
    "Controller",
    "ReactiveController",
    "RecurrentController",
    "SpikingController",
    "make_controller",
]
