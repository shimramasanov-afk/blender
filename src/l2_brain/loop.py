from __future__ import annotations

import time

from l2_brain.config import StandConfig
from l2_brain.controllers.base import Controller
from l2_brain.env.synthetic import SyntheticEnv
from l2_brain.types import Action, EpisodeReport, Observation, TickMetrics


class ControlLoop:
    def __init__(self, env: SyntheticEnv, controller: Controller, config: StandConfig | None = None) -> None:
        self.env = env
        self.controller = controller
        self.config = config or env.config

    def run_episode(self, seed: int | None = None) -> EpisodeReport:
        t_obs0 = time.perf_counter()
        observation = self.env.reset(seed)
        observe_first = (time.perf_counter() - t_obs0) * 1000.0
        self.controller.reset(seed)

        infer: list[float] = []
        loop: list[float] = []
        observe = [observe_first]
        act: list[float] = []
        turns: list[float] = []
        success = False
        stuck = False
        truncated = False
        stuck_reason: str | None = None
        ticks = 0

        for _ in range(self.config.max_steps):
            t_loop = time.perf_counter()
            t0 = time.perf_counter()
            action = self.controller.step(observation).clipped()
            infer_ms = (time.perf_counter() - t0) * 1000.0
            t1 = time.perf_counter()
            observation, info = self.env.step(action)
            act_ms = (time.perf_counter() - t1) * 1000.0
            observe_ms = 0.0
            loop_ms = (time.perf_counter() - t_loop) * 1000.0

            infer.append(infer_ms)
            act.append(act_ms)
            observe.append(observe_ms)
            loop.append(loop_ms)
            turns.append(action.turn)
            ticks += 1
            _ = TickMetrics(observe_ms, infer_ms, act_ms, loop_ms)

            if self.env.scenario == "memory_probe" and ticks >= 16:
                success = self.env.memory_probe_success(turns)
                truncated = not success
                break
            if info.success:
                success = True
                break
            if info.stuck:
                stuck = True
                stuck_reason = info.stuck_reason
                break
            if info.truncated:
                truncated = True
                break
        else:
            truncated = not success

        return EpisodeReport(
            controller=self.controller.name,
            scenario=self.env.scenario,
            seed=-1 if seed is None else seed,
            success=success,
            stuck=stuck,
            truncated=truncated,
            ticks=ticks,
            stuck_reason=stuck_reason,
            infer_ms=tuple(infer),
            loop_ms=tuple(loop),
            observe_ms=tuple(observe),
            act_ms=tuple(act),
        )


def run_episode(env: SyntheticEnv, controller: Controller, seed: int | None = None) -> EpisodeReport:
    return ControlLoop(env, controller).run_episode(seed)


def blank_action() -> Action:
    return Action(turn=0.0, forward=0.0, engage=0.0)


def assert_observation_is_official(observation: Observation) -> None:
    forbidden = {"agent_xy", "target_xy", "distance", "bearing", "hp"}
    extra = forbidden.intersection(observation.__dataclass_fields__)
    if extra:
        raise AssertionError(f"Observation leaked privileged fields: {extra}")
