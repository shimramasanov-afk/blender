from __future__ import annotations

import numpy as np

from l2_brain.capture.profile import WindowProfile


def apply_profile(image: np.ndarray, profile: WindowProfile) -> np.ndarray:
    """Crop ROI and fill named masks. Coordinates come only from the profile."""
    height, width = image.shape[:2]
    x0, y0, x1, y1 = profile.roi.pixel_box(width, height)
    if x1 <= x0 or y1 <= y0:
        cropped = image
    else:
        cropped = image[y0:y1, x0:x1].copy()
    out = np.ascontiguousarray(cropped)
    fill = np.array(profile.mask_fill, dtype=np.uint8)
    ch, cw = out.shape[:2]
    for mask in profile.masks:
        mx0, my0, mx1, my1 = mask.rect.pixel_box(cw, ch)
        if mx1 > mx0 and my1 > my0:
            out[my0:my1, mx0:mx1] = fill
    return out
