from __future__ import annotations

import math
from dataclasses import dataclass

from l2_brain.sim.config import SimConfig


@dataclass(frozen=True, slots=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    kind: str = "wall"

    def contains_point(self, x: float, y: float, pad: float = 0.0) -> bool:
        return (self.x0 - pad) <= x <= (self.x1 + pad) and (self.y0 - pad) <= y <= (self.y1 + pad)


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def circle_hits_box(x: float, y: float, radius: float, box: Box) -> bool:
    nx = min(max(x, box.x0), box.x1)
    ny = min(max(y, box.y0), box.y1)
    return (x - nx) ** 2 + (y - ny) ** 2 < radius * radius


def collides(x: float, y: float, walls: tuple[Box, ...], config: SimConfig) -> bool:
    r = config.agent_radius
    if x < r or y < r or x > config.world - r or y > config.world - r:
        return True
    return any(circle_hits_box(x, y, r, box) for box in walls)


def ray_aabb_xy(ox: float, oy: float, dx: float, dy: float, box: Box) -> float | None:
    inv_x = 1e9 if abs(dx) < 1e-9 else 1.0 / dx
    inv_y = 1e9 if abs(dy) < 1e-9 else 1.0 / dy
    tx1 = (box.x0 - ox) * inv_x
    tx2 = (box.x1 - ox) * inv_x
    ty1 = (box.y0 - oy) * inv_y
    ty2 = (box.y1 - oy) * inv_y
    tmin = max(min(tx1, tx2), min(ty1, ty2))
    tmax = min(max(tx1, tx2), max(ty1, ty2))
    if tmax < 0.0 or tmin > tmax:
        return None
    hit = tmin if tmin > 1e-4 else tmax
    return hit if hit > 1e-4 else None


def ray_circle_xy(ox: float, oy: float, dx: float, dy: float, cx: float, cy: float, radius: float) -> float | None:
    fx = ox - cx
    fy = oy - cy
    a = dx * dx + dy * dy
    if a < 1e-12:
        return None
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return None
    root = math.sqrt(disc)
    t0 = (-b - root) / (2.0 * a)
    t1 = (-b + root) / (2.0 * a)
    for t in (t0, t1):
        if t > 1e-4:
            return t
    return None
