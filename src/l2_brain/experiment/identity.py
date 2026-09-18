from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from l2_brain import __version__

OFFLINE_REPLAY_LIMIT = (
    "Offline replay compares controller outputs on identical recorded "
    "observations. It does not prove an alternative policy would succeed, "
    "because its actions would have changed future frames."
)


def code_identity(root: Path | None = None) -> dict[str, Any]:
    here = root or Path(__file__).resolve().parents[3]
    info: dict[str, Any] = {
        "package": "l2_brain",
        "package_version": __version__,
        "git_rev": None,
        "git_dirty": None,
    }
    try:
        rev = subprocess.check_output(
            ["git", "-C", str(here), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        info["git_rev"] = rev or None
        dirty = subprocess.check_output(
            ["git", "-C", str(here), "status", "--porcelain"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        info["git_dirty"] = bool(dirty.strip())
    except (OSError, subprocess.CalledProcessError):
        pass
    return info


def public_circuit_config(config: Any) -> dict[str, Any]:
    return {
        "seed": config.seed,
        "ticks": config.ticks,
        "tick_hz": config.tick_hz,
        "frame_h": config.frame_h,
        "frame_w": config.frame_w,
        "max_intent_age_ns": config.max_intent_age_ns,
        "stale_frame_ns": config.stale_frame_ns,
        "source_id": config.source_id,
        "record_path": str(config.record_path) if config.record_path else None,
        "strafe_supported": config.strafe_supported,
        "keep_frames": getattr(config, "keep_frames", "none"),
        "frame_every": getattr(config, "frame_every", 1),
        "writer_bound": getattr(config, "writer_bound", 128),
        "model_version": getattr(config, "model_version", "unknown"),
        "gpu_sync": getattr(config, "gpu_sync", False),
    }
