"""Policy-side channel gates. Vision metrics stay on the raw encoder output."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from l2_brain.contracts import Observation
from l2_brain.vision.channels import NavigationChannels, ScaleChannels

ChannelSet = Literal["target", "target_flow", "target_expansion", "all"]

CHANNEL_SETS: tuple[str, ...] = ("target", "target_flow", "target_expansion", "all")


def apply_channel_ablation(observation: Observation, channels: str) -> Observation:
    if channels not in CHANNEL_SETS:
        raise ValueError(f"unknown channel set {channels!r}; choose from {CHANNEL_SETS}")
    if channels == "all":
        return observation
    if channels == "target":
        return replace(
            observation,
            navigation=None,
            motion_estimate=None,
            motion_confidence=0.0,
            validity_mask=replace(observation.validity_mask, motion=False),
        )
    nav = observation.navigation
    if not isinstance(nav, NavigationChannels):
        return observation
    if channels == "target_flow":
        return replace(observation, navigation=_without_expansion(nav))
    return replace(observation, navigation=_without_flow(nav))


def _without_expansion(nav: NavigationChannels) -> NavigationChannels:
    return replace(
        nav,
        expansion=0.0,
        far=replace(nav.far, expansion=0.0),
        near=replace(nav.near, expansion=0.0),
        hypothesis=replace(nav.hypothesis, body_forward_like=0.0),
    )


def _without_flow(nav: NavigationChannels) -> NavigationChannels:
    far = _zero_flow_scale(nav.far)
    near = _zero_flow_scale(nav.near)
    n = len(near.brightness)
    blank = (0.0,) * n
    far = replace(far, brightness=blank, contrast=blank)
    near = replace(near, brightness=blank, contrast=blank)
    return replace(
        nav,
        far=far,
        near=near,
        motion_confidence=0.0,
        flow_absent_is_not_clear=True,
        hypothesis=replace(
            nav.hypothesis,
            camera_yaw_like=0.0,
            residual_object_like=0.0,
            label="uncertain",
        ),
    )


def _zero_flow_scale(scale: ScaleChannels) -> ScaleChannels:
    n = len(scale.flow_u)
    blank = (0.0,) * n
    return replace(
        scale,
        d_pos=blank,
        d_neg=blank,
        flow_u=blank,
        flow_v=blank,
        motion_confidence=0.0,
        valid_flow_frac=0.0,
        weak_texture_frac=1.0,
    )
