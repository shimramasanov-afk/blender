"""Explicit component assembly. Differences must show up in reports."""

from __future__ import annotations

ENCODER_NAMES = ("color_blob", "navigation_v1")


def build_encoder(name: str):
    if name == "color_blob":
        from l2_brain.circuit.encode import ColorBlobEncoder

        return ColorBlobEncoder()
    if name == "navigation_v1":
        from l2_brain.vision.encoder import NavigationEncoder

        return NavigationEncoder()
    raise ValueError(f"unknown encoder {name!r}; choose from {ENCODER_NAMES}")
