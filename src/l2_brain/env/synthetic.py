from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from l2_brain.config import StandConfig
from l2_brain.types import Action, Observation, StepInfo


@dataclass(slots=True)
class _Box:
    x0: float
    y0: float
    x1: float
    y1: float

    def contains(self, x: float, y: float, pad: float = 0.0) -> bool:
        return (self.x0 - pad) <= x <= (self.x1 + pad) and (self.y0 - pad) <= y <= (self.y1 + pad)


@dataclass(slots=True)
class SyntheticEnv:
    """Egocentric visual stand. Privileged pose is only in StepInfo."""

    scenario: str = "open_field"
    config: StandConfig = field(default_factory=StandConfig)
    _rng: np.random.Generator = field(init=False, repr=False)
    _tick: int = field(init=False, default=0)
    _x: float = field(init=False, default=3.5)
    _y: float = field(init=False, default=8.0)
    _yaw: float = field(init=False, default=0.0)
    _tx: float = field(init=False, default=9.0)
    _ty: float = field(init=False, default=8.0)
    _target_visible: bool = field(init=False, default=True)
    _walls: list[_Box] = field(init=False, default_factory=list)
    _xs: list[float] = field(init=False, default_factory=list)
    _ys: list[float] = field(init=False, default_factory=list)
    _yaws: list[float] = field(init=False, default_factory=list)
    _dists: list[float] = field(init=False, default_factory=list)
    _blocked: list[bool] = field(init=False, default_factory=list)
    _closed: bool = field(init=False, default=False)

    def reset(self, seed: int | None = None) -> Observation:
        self._rng = np.random.default_rng(seed)
        self._tick = 0
        self._target_visible = True
        self._xs.clear()
        self._ys.clear()
        self._yaws.clear()
        self._dists.clear()
        self._blocked.clear()
        self._closed = False
        self._place(seed)
        return self._observe()

    def step(self, action: Action) -> tuple[Observation, StepInfo]:
        if self._closed:
            raise RuntimeError("env is closed")
        action = action.clipped()
        cfg = self.config
        # Plus turn looks right; yaw is CCW-positive, so right decreases yaw.
        self._yaw = _wrap(self._yaw - action.turn * cfg.max_turn)
        nx = self._x + math.cos(self._yaw) * action.forward * cfg.max_speed
        ny = self._y + math.sin(self._yaw) * action.forward * cfg.max_speed
        blocked = self._collides(nx, ny)
        if not blocked:
            self._x, self._y = nx, ny
        self._move_target()
        self._tick += 1
        info = self._info(action, blocked)
        self._xs.append(self._x)
        self._ys.append(self._y)
        self._yaws.append(self._yaw)
        self._dists.append(info.distance)
        self._blocked.append(blocked)
        info = self._with_stuck(info)
        return self._observe(), info

    def close(self) -> None:
        self._closed = True

    def _place(self, seed: int | None) -> None:
        cfg = self.config
        jitter = seed is not None
        yaw_noise = float(self._rng.normal(0.0, 0.10)) if jitter else 0.0
        y_noise = float(self._rng.normal(0.0, 0.35)) if jitter else 0.0
        self._walls = []
        if self.scenario == "open_field":
            self._x, self._y, self._yaw = 3.5, 8.0, yaw_noise
            self._tx, self._ty = 9.0, 8.0 + y_noise
        elif self.scenario == "pursuit":
            self._x, self._y, self._yaw = 3.5, 8.0, yaw_noise
            self._tx, self._ty = 8.5, 8.4 + y_noise
        elif self.scenario == "occluded":
            self._x, self._y, self._yaw = 3.2, 8.0, yaw_noise
            self._tx, self._ty = 11.0, 8.0 + y_noise
            self._walls = [_Box(6.6, 6.2, 7.4, 10.2)]
        elif self.scenario == "memory_probe":
            self._x, self._y, self._yaw = 4.0, 8.0, 0.0
            self._tx, self._ty = 8.5, 9.8
            self._target_visible = True
        else:
            raise ValueError(f"unknown scenario {self.scenario!r}")
        self._x = float(np.clip(self._x, 1.0, cfg.world - 1.0))
        self._y = float(np.clip(self._y, 1.0, cfg.world - 1.0))

    def _move_target(self) -> None:
        if self.scenario == "pursuit":
            self._ty = float(np.clip(self._ty + 0.035, 2.0, 14.0))
        elif self.scenario == "memory_probe" and self._tick >= 4:
            self._target_visible = False

    def _collides(self, x: float, y: float) -> bool:
        cfg = self.config
        r = cfg.agent_radius
        if x < r or y < r or x > cfg.world - r or y > cfg.world - r:
            return True
        return any(box.contains(x, y, pad=r) for box in self._walls)

    def _geometry(self) -> tuple[float, float]:
        if not self._target_visible:
            return 99.0, 0.0
        dx = self._tx - self._x
        dy = self._ty - self._y
        distance = math.hypot(dx, dy)
        bearing = _wrap(math.atan2(dy, dx) - self._yaw)
        return distance, bearing

    def _info(self, action: Action, blocked: bool) -> StepInfo:
        distance, bearing = self._geometry()
        cfg = self.config
        success = False
        if self.scenario == "memory_probe":
            success = False
        elif (
            self._target_visible
            and action.engage > 0.5
            and distance <= cfg.engage_distance
            and abs(bearing) <= cfg.engage_angle
        ):
            success = True
        truncated = self._tick >= cfg.max_steps and not success
        target_xy = (self._tx, self._ty) if self._target_visible else None
        return StepInfo(
            agent_xy=(self._x, self._y),
            target_xy=target_xy,
            distance=distance,
            bearing=bearing,
            blocked=blocked,
            success=success,
            stuck=False,
            truncated=truncated,
        )

    def _with_stuck(self, info: StepInfo) -> StepInfo:
        if info.success:
            return info
        reason = self._stuck_reason(info)
        if reason is None:
            return info
        return StepInfo(
            agent_xy=info.agent_xy,
            target_xy=info.target_xy,
            distance=info.distance,
            bearing=info.bearing,
            blocked=info.blocked,
            success=False,
            stuck=True,
            truncated=info.truncated,
            stuck_reason=reason,
        )

    def _stuck_reason(self, info: StepInfo) -> str | None:
        cfg = self.config
        if len(self._xs) >= cfg.frozen_window:
            dx = self._xs[-1] - self._xs[-cfg.frozen_window]
            dy = self._ys[-1] - self._ys[-cfg.frozen_window]
            dyaw = abs(_wrap(self._yaws[-1] - self._yaws[-cfg.frozen_window]))
            if math.hypot(dx, dy) < cfg.frozen_xy and dyaw < cfg.frozen_yaw:
                return "frozen"
        if self.scenario == "memory_probe":
            return None
        if len(self._dists) >= cfg.progress_window:
            window = self._dists[-cfg.progress_window :]
            blocked = self._blocked[-cfg.progress_window :]
            if (
                min(window) > window[0] - cfg.progress_eps
                and info.distance > cfg.engage_distance
                and (sum(blocked) / len(blocked)) >= cfg.blocked_frac
            ):
                return "no_progress"
        return None

    def memory_probe_success(self, turns: list[float]) -> bool:
        if self.scenario != "memory_probe" or len(turns) < 16:
            return False
        after = turns[4:16]
        return float(np.mean(after)) < -0.20

    def _observe(self) -> Observation:
        frame = render(
            x=self._x,
            y=self._y,
            yaw=self._yaw,
            tx=self._tx,
            ty=self._ty,
            target_visible=self._target_visible,
            walls=self._walls,
            config=self.config,
        )
        return Observation(frame=frame, timestamp_ns=time.perf_counter_ns(), tick=self._tick)


def render(
    *,
    x: float,
    y: float,
    yaw: float,
    tx: float,
    ty: float,
    target_visible: bool,
    walls: list[_Box],
    config: StandConfig,
) -> np.ndarray:
    h, w = config.frame_h, config.frame_w
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[: h // 2] = (92, 142, 198)
    frame[h // 2 :] = (74, 58, 42)
    max_dist = 14.0
    samples = 72
    target_r2 = config.target_radius ** 2
    for col in range(w):
        ang = yaw + (0.5 - col / max(w - 1, 1)) * config.fov_rad
        dx = math.cos(ang)
        dy = math.sin(ang)
        hit_kind = None
        hit_d = max_dist
        for step in range(1, samples + 1):
            t = max_dist * step / samples
            px = x + dx * t
            py = y + dy * t
            if px < 0.2 or py < 0.2 or px > config.world - 0.2 or py > config.world - 0.2:
                hit_kind, hit_d = "wall", t
                break
            if any(box.contains(px, py) for box in walls):
                hit_kind, hit_d = "wall", t
                break
            if target_visible and (px - tx) ** 2 + (py - ty) ** 2 <= target_r2:
                hit_kind, hit_d = "target", t
                break
        if hit_kind is None:
            continue
        sliver = int(min(h, h * 1.85 / max(hit_d, 0.25)))
        y0 = (h - sliver) // 2
        y1 = y0 + sliver
        shade = max(0.55, 1.0 - hit_d / max_dist)
        if hit_kind == "target":
            color = (int(230 * shade), int(40 * shade), int(36 * shade))
        else:
            color = (int(120 * shade), int(120 * shade), int(128 * shade))
        frame[y0:y1, col] = color
    return frame


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi
