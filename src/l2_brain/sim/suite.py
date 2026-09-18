from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from l2_brain.contracts import MotorIntent
from l2_brain.sim.config import EpisodeSpec, catalog
from l2_brain.sim.environment import SimulationEnvironment, idle_intent
from l2_brain.sim.views import AgentView, EpisodeResult, GroundTruth

Policy = Callable[[AgentView], MotorIntent]

SUITE_NOTE = (
    "Headless synthetic navigation. Results are not a transfer proof for an MMORPG client."
)


def run_episode(spec: EpisodeSpec, policy: Policy) -> EpisodeResult:
    env = SimulationEnvironment(spec)
    env.initialize()
    try:
        view = env.reset_episode(spec)
        success = env.reached_goal()
        timeout = False
        for _ in range(spec.config.max_steps):
            if success:
                break
            intent = policy(view)
            view, _gt = env.step(intent)
            _ = _gt
            success = env.reached_goal()
        else:
            timeout = not success
        return env.result(success=success, timeout=timeout)
    finally:
        env.close()


def run_catalog(
    seed: int,
    policy: Policy,
    *,
    split: str | None = None,
    scenarios: tuple[str, ...] | None = None,
    max_steps: int | None = None,
) -> list[EpisodeResult]:
    specs = catalog(seed)
    if split is not None:
        specs = [s for s in specs if s.split == split]
    if scenarios is not None:
        allowed = set(scenarios)
        specs = [s for s in specs if s.scenario in allowed]
    if max_steps is not None:
        from dataclasses import replace

        specs = [
            EpisodeSpec(
                scenario=s.scenario,
                split=s.split,
                variant=s.variant,
                seed=s.seed,
                config=replace(s.config, max_steps=max_steps),
            )
            for s in specs
        ]
    return [run_episode(spec, policy) for spec in specs]


def write_results(path: Path, results: list[EpisodeResult], *, extras: dict[str, Any] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "suite": "nav-sim-v1",
        "transfer_claim": False,
        "limitation": SUITE_NOTE,
        "episodes": [item.to_dict() for item in results],
        "extras": extras or {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def idle_policy(_view: AgentView) -> MotorIntent:
    return idle_intent()


def assert_no_privileged_in_view(view: AgentView) -> None:
    from l2_brain.contracts import PRIVILEGED_OBSERVATION_FIELDS

    leaked = PRIVILEGED_OBSERVATION_FIELDS.intersection(view.__dataclass_fields__)
    if leaked:
        raise AssertionError(f"AgentView carries privileged fields: {sorted(leaked)}")
    if hasattr(view.frame, "agent_xy") or hasattr(view.frame, "walls"):
        raise AssertionError("Frame carries privileged geometry")


def replay_intents(spec: EpisodeSpec, intents: list[MotorIntent]) -> tuple[list[AgentView], list[GroundTruth]]:
    env = SimulationEnvironment(spec)
    env.initialize()
    views = [env.reset_episode(spec)]
    truths: list[GroundTruth] = []
    try:
        for intent in intents:
            view, gt = env.step(intent)
            views.append(view)
            truths.append(gt)
    finally:
        env.close()
    return views, truths
