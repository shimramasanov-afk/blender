from __future__ import annotations

import numpy as np

from l2_brain.capture.masks import apply_profile
from l2_brain.contracts import EncodedVisual, Frame, Observation, TelemetryEvent, ValidityMask
from l2_brain.experiment.clocks import mono_ns
from l2_brain.features import extract_from_image
from l2_brain.vision.channels import MotionHypothesis, NavigationChannels, ScaleChannels, hypothesis_from_flow
from l2_brain.vision.config import VisionConfig
from l2_brain.vision.diagnose import render_diag
from l2_brain.vision.flow import FlowField, expansion, mean_flow, reference_flow, scale_expansion
from l2_brain.vision.preprocess import normalize_01, prepare, scene_correlation, sector_stats


class NavigationEncoder:
    """Interpretable CPU encoder. No object-recognition network."""

    name = "navigation_v1"

    def __init__(self, config: VisionConfig | None = None) -> None:
        self.config = config or VisionConfig()
        self._open = False
        self._prev_gray = None
        self._prev_id: int | None = None
        self._flow_suppress = 0
        self.last_diag = None
        self.last_channels: NavigationChannels | None = None
        self.last_flow: FlowField | None = None
        self.last_preprocess_ms = 0.0

    def initialize(self) -> None:
        self._open = True
        self.reset_episode(None)

    def reset_episode(self, seed: int | None = None) -> None:
        self._prev_gray = None
        self._prev_id = None
        self._flow_suppress = 0
        self.last_diag = None
        self.last_channels = None
        self.last_flow = None

    def encode(
        self,
        frame: Frame,
        telemetry: tuple[TelemetryEvent, ...],
        previous: Observation | None,
        now_ns: int,
        stale: bool,
    ) -> Observation:
        if not self._open:
            raise RuntimeError("NavigationEncoder is closed")
        if frame.image is None:
            raise ValueError("encoder needs an in-memory image")
        started = mono_ns()
        profile = self.config.profile
        # All visual channels share the same ROI/masks, including target detection.
        work = apply_profile(frame.image, profile) if profile is not None else frame.image
        gray = prepare(work, self.config, None)
        gray01 = normalize_01(gray)
        blob = extract_from_image(work)
        hold_flow = stale or self._flow_suppress > 0
        if stale:
            # A missing image is not a temporal reference. Resume with a fresh
            # baseline; do not interpret a multi-tick gap as one tick of flow.
            self._prev_gray = None
            self._prev_id = None
            self._flow_suppress = self.config.stale_flow_hold
        elif self._flow_suppress > 0:
            self._flow_suppress -= 1
        target_conf = min(1.0, blob.mass * 8.0) if blob.seen else 0.0
        bearing = None
        if blob.seen and blob.centroid is not None:
            bearing = float((blob.centroid - 0.5) * self.config.fov_rad)
        duplicate = False
        abrupt = False
        lighting = 0.0
        field: FlowField | None = None
        if self._prev_gray is not None and self._prev_id == frame.frame_id:
            duplicate = True
        if self._prev_gray is not None and not duplicate and not hold_flow:
            delta = gray01 - normalize_01(self._prev_gray)
            l1 = float(np_abs_mean(delta))
            lighting = abs(float(delta.mean()))
            corr = scene_correlation(self._prev_gray, gray)
            if l1 < self.config.duplicate_l1:
                duplicate = True
            if not duplicate:
                field = reference_flow(self._prev_gray, gray, self.config)
                _u, _v, motion_guess = mean_flow(field)
                if l1 > self.config.abrupt_l1 and corr < self.config.abrupt_corr and motion_guess < 0.12:
                    abrupt = True
        preprocess_ms = (mono_ns() - started) / 1_000_000.0
        self.last_preprocess_ms = preprocess_ms
        prev01 = None if self._prev_gray is None else normalize_01(self._prev_gray)
        far = self._scale("far", gray01, field, prev01)
        near_field = None
        if field is not None and self._prev_gray is not None and not duplicate and not abrupt:
            y0 = int(self.config.near_y0 * gray.shape[0])
            if gray.shape[0] - y0 >= 12:
                near_field = reference_flow(self._prev_gray[y0:], gray[y0:], self.config)
        near = self._near(gray01, near_field, prev01)
        if field is None or duplicate or abrupt or stale or hold_flow:
            mean_u, motion_c, exp = 0.0, 0.0, 0.0
            hypo = hypothesis_from_flow(
                _empty_field(),
                previous=previous.previous_action if previous else None,
            )
            if stale or duplicate or abrupt or hold_flow:
                hypo = MotionHypothesis(
                    camera_yaw_like=0.0,
                    body_forward_like=0.0,
                    residual_object_like=0.0,
                    command_prior_used=previous is not None,
                    command_is_not_measurement=True,
                    label="low_confidence",
                )
        else:
            mean_u, _mean_v, flow_c = mean_flow(field)
            exp, scale_c = scale_expansion(self._prev_gray, gray, self.config.scale_conf_min)
            motion_c = max(flow_c, scale_c)
            hypo = hypothesis_from_flow(
                field,
                previous=previous.previous_action if previous else None,
                expansion_v=exp,
                motion_c=motion_c,
            )
        weak_frac = far.weak_texture_frac
        flow_absent = field is None or far.valid_flow_frac < 0.15 or weak_frac > 0.55
        channels = NavigationChannels(
            preprocess_ms=preprocess_ms,
            width=self.config.width,
            height=self.config.height,
            sectors_x=self.config.sectors_x,
            sectors_y=self.config.sectors_y,
            far=far,
            near=near,
            target_bearing=None if stale else bearing,
            target_confidence=0.0 if stale else target_conf,
            motion_confidence=0.0 if stale or duplicate or abrupt or hold_flow else motion_c,
            expansion=0.0 if stale or duplicate or abrupt or hold_flow else exp,
            flow_absent_is_not_clear=True,
            duplicate_frame=duplicate,
            abrupt_cut=abrupt,
            lighting_change=lighting,
            hypothesis=hypo,
            no_object_model=True,
        )
        self.last_channels = channels
        self.last_flow = field
        if self.config.diagnose and field is not None:
            self.last_diag = render_diag(
                gray,
                field,
                channels,
                target_x=blob.centroid,
            )
        visual = EncodedVisual(
            left=blob.left,
            center=blob.center,
            right=blob.right,
            centroid=blob.centroid,
            mass=blob.mass,
            confidence=target_conf,
        )
        motion_est = None if stale or duplicate or abrupt or hold_flow else float(mean_u)
        mask = ValidityMask(
            frame=True,
            visual_features=True,
            target=blob.seen and not stale,
            motion=motion_est is not None and motion_c > 0.08,
            telemetry=True,
            previous_action=previous is not None,
            stale=stale,
            duplicate=duplicate,
        )
        self._prev_gray = None if stale else gray
        self._prev_id = None if stale else frame.frame_id
        return Observation(
            timestamp_ns=now_ns,
            frame_id=frame.frame_id,
            visual_features=visual,
            target_bearing=channels.target_bearing,
            target_confidence=channels.target_confidence,
            motion_estimate=motion_est,
            motion_confidence=channels.motion_confidence,
            telemetry=telemetry,
            validity_mask=mask,
            previous_action=previous.previous_action if previous else None,
            navigation=channels,
        )

    def close(self) -> None:
        self._open = False
        self.reset_episode(None)

    def _scale(self, name: str, gray01, field: FlowField | None, prev01) -> ScaleChannels:
        cfg = self.config
        bright, contrast = sector_stats(gray01, cfg.sectors_x, cfg.sectors_y)
        if prev01 is None:
            zeros = tuple(0.0 for _ in bright)
            d_pos = d_neg = zeros
        else:
            delta = gray01 - prev01
            d_pos, _ = sector_stats(np_clip_pos(delta), cfg.sectors_x, cfg.sectors_y)
            d_neg, _ = sector_stats(np_clip_pos(-delta), cfg.sectors_x, cfg.sectors_y)
        if field is None:
            flow_u = tuple(0.0 for _ in range(cfg.flow_nx * cfg.flow_ny))
            flow_v = flow_u
            exp = 0.0
            motion_c = 0.0
            weak = 1.0
            valid = 0.0
        else:
            flow_u = tuple(float(v) for v in field.u.ravel())
            flow_v = tuple(float(v) for v in field.v.ravel())
            exp = expansion(field)
            _u, _v, motion_c = mean_flow(field)
            weak = float(field.weak_texture.mean())
            valid = float(((~field.weak_texture) & (field.confidence > 0.08)).mean())
        return ScaleChannels(
            name=name,
            brightness=tuple(b / 1.0 for b in bright),
            contrast=contrast,
            d_pos=d_pos,
            d_neg=d_neg,
            flow_u=flow_u,
            flow_v=flow_v,
            expansion=exp,
            motion_confidence=motion_c,
            weak_texture_frac=weak,
            valid_flow_frac=valid,
        )

    def _near(self, gray01, field: FlowField | None, prev01) -> ScaleChannels:
        y0 = int(self.config.near_y0 * gray01.shape[0])
        crop = gray01[y0:, :]
        prev_crop = None if prev01 is None else prev01[y0:, :]
        return self._scale("near", crop, field, prev_crop)


def np_abs_mean(arr) -> float:
    import numpy as np

    return float(np.mean(np.abs(arr)))


def np_clip_pos(arr):
    import numpy as np

    return np.maximum(arr, 0.0)


def _empty_field() -> FlowField:
    import numpy as np

    z = np.zeros((1, 1), dtype=np.float32)
    return FlowField(u=z, v=z, confidence=z, weak_texture=np.ones((1, 1), dtype=bool), xs=z, ys=z)
