from __future__ import annotations

from dataclasses import dataclass

from l2_brain.capture.profile import WindowProfile


@dataclass(frozen=True, slots=True)
class VisionConfig:
    """Small working image and sector grid. Values are chosen after a local bench."""

    width: int = 48
    height: int = 32
    sectors_x: int = 5
    sectors_y: int = 3
    flow_nx: int = 8
    flow_ny: int = 6
    flow_block: int = 5
    flow_search: int = 8
    flow_smooth: float = 2.5
    near_y0: float = 0.45
    texture_var: float = 8.0
    scale_conf_min: float = 0.10
    abrupt_l1: float = 0.22
    abrupt_corr: float = 0.12
    duplicate_l1: float = 0.006
    lighting_l1: float = 0.08
    fov_rad: float = 1.2
    stale_flow_hold: int = 2
    diagnose: bool = False
    profile: WindowProfile | None = None

    def __post_init__(self) -> None:
        if self.width < 16 or self.height < 12:
            raise ValueError("working image too small")
        if self.sectors_x < 3 or self.sectors_y < 1:
            raise ValueError("need at least 3x1 sectors")
        if self.flow_search < 1 or self.flow_block < 3:
            raise ValueError("flow block/search too small")
        if self.stale_flow_hold < 0:
            raise ValueError("stale_flow_hold must be >= 0")


STARTER = VisionConfig()

CANDIDATES = (
    VisionConfig(width=32, height=24, sectors_x=5, sectors_y=3, flow_nx=6, flow_ny=4, flow_search=5),
    VisionConfig(width=48, height=32, sectors_x=5, sectors_y=3, flow_nx=8, flow_ny=6, flow_search=8),
    VisionConfig(width=64, height=48, sectors_x=7, sectors_y=3, flow_nx=10, flow_ny=8, flow_search=9),
)
