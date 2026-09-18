from __future__ import annotations

from l2_brain.contracts import EncodedVisual, Frame, Observation, TelemetryEvent, ValidityMask
from l2_brain.features import extract_from_image


class ColorBlobEncoder:
    """CPU colour-blob encoder. Bearing is from pixels, not simulator pose."""

    def __init__(self, fov_rad: float = 1.2) -> None:
        self._fov = fov_rad
        self._prev_centroid: float | None = None
        self._open = False

    def initialize(self) -> None:
        self._open = True
        self.reset_episode(None)

    def reset_episode(self, seed: int | None = None) -> None:
        self._prev_centroid = None

    def encode(
        self,
        frame: Frame,
        telemetry: tuple[TelemetryEvent, ...],
        previous: Observation | None,
        now_ns: int,
        stale: bool,
    ) -> Observation:
        if not self._open:
            raise RuntimeError("ColorBlobEncoder is closed")
        if frame.image is None:
            raise ValueError("encoder needs an in-memory image in the mock circuit")
        raw = extract_from_image(frame.image)
        seen = raw.seen
        confidence = min(1.0, raw.mass * 8.0) if seen else 0.0
        visual = EncodedVisual(
            left=raw.left,
            center=raw.center,
            right=raw.right,
            centroid=raw.centroid,
            mass=raw.mass,
            confidence=confidence,
        )
        bearing = None
        if seen and raw.centroid is not None:
            bearing = float((raw.centroid - 0.5) * self._fov)
        motion = None
        motion_c = 0.0
        if seen and raw.centroid is not None and self._prev_centroid is not None:
            motion = float(raw.centroid - self._prev_centroid)
            motion_c = min(1.0, confidence)
        if seen:
            self._prev_centroid = raw.centroid
        mask = ValidityMask(
            frame=frame.image is not None,
            visual_features=True,
            target=seen and not stale,
            motion=motion is not None and not stale,
            telemetry=True,
            previous_action=previous is not None,
            stale=stale,
        )
        return Observation(
            timestamp_ns=now_ns,
            frame_id=frame.frame_id,
            visual_features=visual,
            target_bearing=bearing if not stale else None,
            target_confidence=0.0 if stale else float(confidence),
            motion_estimate=None if stale else motion,
            motion_confidence=0.0 if stale else motion_c,
            telemetry=telemetry,
            validity_mask=mask,
            previous_action=previous.previous_action if previous else None,
        )

    def close(self) -> None:
        self._open = False
        self._prev_centroid = None
