from __future__ import annotations


def should_keep_frame(tick: int, keep_frames: str, frame_every: int) -> bool:
    if keep_frames == "none":
        return False
    if keep_frames == "all":
        return True
    if keep_frames == "every":
        if frame_every < 1:
            raise ValueError("frame_every must be >= 1")
        return tick % frame_every == 0
    raise ValueError(f"unknown keep_frames {keep_frames!r}")
