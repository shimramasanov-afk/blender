from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from l2_brain.types import Observation


@dataclass(frozen=True, slots=True)
class VisualFeatures:
    left: float
    center: float
    right: float
    centroid: float | None
    mass: float

    @property
    def seen(self) -> bool:
        return self.mass > 0.002 and self.centroid is not None


def red_mask(frame: np.ndarray) -> np.ndarray:
    r = frame[:, :, 0].astype(np.int16)
    g = frame[:, :, 1].astype(np.int16)
    b = frame[:, :, 2].astype(np.int16)
    return (r - g > 40) & (r - b > 40) & (r > 45)


def extract_from_image(image: np.ndarray) -> VisualFeatures:
    mask = red_mask(image)
    _height, width = mask.shape
    third = width // 3
    left = float(mask[:, :third].mean())
    center = float(mask[:, third : 2 * third].mean())
    right = float(mask[:, 2 * third :].mean())
    mass = float(mask.mean())
    xs = np.flatnonzero(mask.any(axis=0))
    centroid = float(xs.mean() / max(width - 1, 1)) if xs.size else None
    return VisualFeatures(
        left=left,
        center=center,
        right=right,
        centroid=centroid,
        mass=mass,
    )


def extract(observation: Observation) -> VisualFeatures:
    return extract_from_image(observation.frame)
