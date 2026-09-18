from __future__ import annotations

import math
from collections import deque
from dataclasses import replace

from l2_brain.contracts import Frame, MotorIntent
from l2_brain.sim.camera import render_perspective
from l2_brain.sim.config import EpisodeSpec, SimConfig
from l2_brain.sim.scenarios import Layout, layout_for
from l2_brain.sim.views import AgentView, EpisodeResult, GroundTruth
from l2_brain.sim.world import Box, collides, wrap

TRANSFER_LIMIT = (
    "synthetic perspective stand; success here is not evidence of MMORPG transfer"
)


class SimulationEnvironment:
    """Headless navigation stand. Agent sees images; evaluator sees GroundTruth."""

    def __init__(self, spec: EpisodeSpec) -> None:
        self.spec = spec
        self._open = False
        self._tick = 0
        self._cfg = spec.config
        self._layout: Layout | None = None
        self._x = 0.0
        self._y = 0.0
        self._body_yaw = 0.0
        self._camera_yaw = 0.0
        self._gx = 0.0
        self._gy = 0.0
        self._walls: tuple[Box, ...] = ()
        self._goal_visible = True
        self._pending: deque[MotorIntent] = deque()
        self.last_applied_intent = _zero_intent(0)
        self._last_image = None
        self._path = 0.0
        self._collisions = 0
        self._contacts = 0
        self._dir_changes = 0
        self._last_turn_sign = 0
        self._dists: list[float] = []
        self._xs: list[float] = []
        self._ys: list[float] = []

    def initialize(self) -> None:
        self._open = True

    def reset_episode(self, spec: EpisodeSpec | None = None) -> AgentView:
        if spec is not None:
            self.spec = spec
            self._cfg = spec.config
        if not self._open:
            self.initialize()
        layout = layout_for(self.spec)
        self._layout = layout
        cfg = self._effective_config(layout)
        self._cfg = cfg
        self._tick = 0
        self._x, self._y = cfg.start_xy or layout.start_xy
        self._body_yaw = layout.start_yaw if cfg.start_yaw is None else cfg.start_yaw
        self._camera_yaw = self._body_yaw
        self._gx, self._gy = cfg.goal_xy or layout.goal_xy
        self._walls = layout.walls
        self._goal_visible = True
        self._pending.clear()
        self.last_applied_intent = _zero_intent(0)
        self._path = 0.0
        self._collisions = 0
        self._contacts = 0
        self._dir_changes = 0
        self._last_turn_sign = 0
        self._dists.clear()
        self._xs.clear()
        self._ys.clear()
        self._last_image = None
        return self._view(dropped=False, delayed=False)

    def step(self, intent: MotorIntent) -> tuple[AgentView, GroundTruth]:
        if not self._open or self._layout is None:
            raise RuntimeError("environment is not initialized")
        intent = intent.clipped()
        delay = self._cfg.action_delay_ticks
        delayed = delay > 0
        self._pending.append(intent)
        if len(self._pending) <= delay:
            applied = _zero_intent(intent.valid_until_ns)
        else:
            applied = self._pending.popleft()
            delayed = delay > 0
        self.last_applied_intent = applied
        contact = self._integrate(applied)
        self._tick += 1
        if self._layout.hide_goal_after is not None and self._tick >= self._layout.hide_goal_after:
            self._goal_visible = False
        if self._layout.goal_delta is not None:
            self._gx += self._layout.goal_delta[0]
            self._gy += self._layout.goal_delta[1]
        dropped = self._tick in self._cfg.drop_ticks
        view = self._view(dropped=dropped, delayed=delayed)
        gt = self._truth(contact=contact, dropped=dropped, delayed=delayed)
        self._dists.append(gt.distance_to_goal)
        self._xs.append(self._x)
        self._ys.append(self._y)
        return view, gt

    def result(self, *, success: bool, timeout: bool) -> EpisodeResult:
        no_progress = self._no_progress()
        terminal = "success" if success else ("timeout" if timeout else "running")
        return EpisodeResult(
            episode_id=self.spec.episode_id,
            scenario=self.spec.scenario,
            split=self.spec.split,
            variant=self.spec.variant,
            seed=self.spec.seed,
            config=self.spec.to_dict() | {"resolved_config": self._cfg.to_dict()},
            success=success,
            timeout=timeout,
            collisions=self._collisions,
            no_progress=no_progress,
            path_length=self._path,
            time_s=self._tick / self._cfg.tick_hz,
            direction_changes=self._dir_changes,
            ticks=self._tick,
            terminal=terminal,
            transfer_claim=False,
            limitation=TRANSFER_LIMIT,
        )

    def close(self) -> None:
        self._open = False
        self._pending.clear()

    def _effective_config(self, layout: Layout) -> SimConfig:
        cfg = self.spec.config
        return replace(
            cfg,
            texture_strength=layout.texture_strength if layout.texture_strength is not None else cfg.texture_strength,
            lighting=layout.lighting if layout.lighting is not None else cfg.lighting,
            action_delay_ticks=(
                layout.action_delay_ticks if layout.action_delay_ticks is not None else cfg.action_delay_ticks
            ),
            drop_ticks=layout.drop_ticks if layout.drop_ticks is not None else cfg.drop_ticks,
        )

    def _integrate(self, intent: MotorIntent) -> bool:
        cfg = self._cfg
        layout = self._layout
        assert layout is not None
        if intent.stop == "fire":
            turn = 0.0
            forward = 0.0
        else:
            turn = intent.turn
            forward = intent.forward
        sign = 0 if abs(turn) < 0.05 else (1 if turn > 0 else -1)
        if sign != 0 and self._last_turn_sign != 0 and sign != self._last_turn_sign:
            self._dir_changes += 1
        if sign != 0:
            self._last_turn_sign = sign
        self._camera_yaw = wrap(self._camera_yaw - turn * cfg.max_turn)
        if not layout.camera_only_turn:
            self._body_yaw = wrap(self._body_yaw - turn * cfg.max_turn)
        nx = self._x + math.cos(self._body_yaw) * forward * cfg.max_speed
        ny = self._y + math.sin(self._body_yaw) * forward * cfg.max_speed
        if intent.strafe is not None:
            nx += math.cos(self._body_yaw + math.pi / 2) * intent.strafe * cfg.max_speed
            ny += math.sin(self._body_yaw + math.pi / 2) * intent.strafe * cfg.max_speed
        contact = collides(nx, ny, self._walls, cfg)
        if contact:
            self._collisions += 1
            self._contacts += 1
            return True
        self._path += math.hypot(nx - self._x, ny - self._y)
        self._x, self._y = nx, ny
        return False

    def _view(self, *, dropped: bool, delayed: bool) -> AgentView:
        image = render_perspective(
            x=self._x,
            y=self._y,
            camera_yaw=self._camera_yaw,
            goal_x=self._gx,
            goal_y=self._gy,
            goal_visible=self._goal_visible,
            walls=self._walls,
            config=self._cfg,
        )
        if dropped:
            # Timestamp still advances; pixels are not a silent copy.
            image = image.copy()
            image[:] = 0
        self._last_image = image
        period = int(1_000_000_000 / self._cfg.tick_hz)
        capture = 1_000_000_000 + self._tick * period
        received = capture + 1500
        frame = Frame(
            frame_id=self._tick + 1,
            timestamp_capture_ns=capture,
            timestamp_received_ns=received,
            width=self._cfg.frame_w,
            height=self._cfg.frame_h,
            pixel_format="rgb8",
            source_id=self._cfg.source_id,
            image=image,
        )
        return AgentView(frame=frame, dropped=dropped, action_delayed=delayed)

    def _truth(self, *, contact: bool, dropped: bool, delayed: bool) -> GroundTruth:
        dist = math.hypot(self._gx - self._x, self._gy - self._y)
        return GroundTruth(
            tick=self._tick,
            agent_xy=(self._x, self._y),
            body_yaw=self._body_yaw,
            camera_yaw=self._camera_yaw,
            goal_xy=(self._gx, self._gy),
            distance_to_goal=dist,
            obstacle_contact=contact,
            goal_visible=self._goal_visible,
            dropped_frame=dropped,
            action_delayed=delayed,
            walls=tuple((b.x0, b.y0, b.x1, b.y1) for b in self._walls),
        )

    def reached_goal(self) -> bool:
        return math.hypot(self._gx - self._x, self._gy - self._y) <= self._cfg.goal_radius

    def _no_progress(self) -> bool:
        if len(self._dists) < 25:
            return False
        window = self._dists[-25:]
        return min(window) > window[0] - 0.12


def _zero_intent(valid_until_ns: int) -> MotorIntent:
    return MotorIntent(
        turn=0.0,
        forward=0.0,
        stop="idle",
        select_target="idle",
        attack="idle",
        confidence=0.0,
        valid_until_ns=valid_until_ns,
    )


def idle_intent(now_ns: int = 10**15) -> MotorIntent:
    return MotorIntent(
        turn=0.0,
        forward=0.0,
        stop="idle",
        select_target="idle",
        attack="idle",
        confidence=1.0,
        valid_until_ns=now_ns,
    )


def forward_intent(now_ns: int = 10**15) -> MotorIntent:
    return MotorIntent(
        turn=0.0,
        forward=1.0,
        stop="idle",
        select_target="idle",
        attack="idle",
        confidence=1.0,
        valid_until_ns=now_ns,
    )


def turn_intent(turn: float, now_ns: int = 10**15) -> MotorIntent:
    return MotorIntent(
        turn=turn,
        forward=0.0,
        stop="idle",
        select_target="idle",
        attack="idle",
        confidence=1.0,
        valid_until_ns=now_ns,
    )
