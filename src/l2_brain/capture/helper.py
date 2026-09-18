from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from l2_brain.capture.errors import CaptureError, PermissionDenied

HELPER_NAME = "capture-probe"
SCK_MINIMUM = "12.3"
SOURCE_FILES = (
    "Packet.swift",
    "Permission.swift",
    "TestWindow.swift",
    "Streamer.swift",
    "main.swift",
)


def default_helper_path(root: Path | None = None) -> Path:
    here = root or Path(__file__).resolve().parents[3]
    return here / ".build" / HELPER_NAME


def helper_sources(root: Path | None = None) -> list[Path]:
    here = root or Path(__file__).resolve().parents[3]
    base = here / "macos" / "CaptureProbe"
    return [base / name for name in SOURCE_FILES]


def build_helper(root: Path | None = None) -> Path:
    here = root or Path(__file__).resolve().parents[3]
    dest = default_helper_path(here)
    dest.parent.mkdir(parents=True, exist_ok=True)
    sources = helper_sources(here)
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        raise CaptureError(f"Swift sources missing: {missing}")
    cmd = [
        "swiftc",
        "-parse-as-library",
        "-O",
        "-o",
        str(dest),
        *[str(path) for path in sources],
        "-framework",
        "ScreenCaptureKit",
        "-framework",
        "Foundation",
        "-framework",
        "CoreGraphics",
        "-framework",
        "CoreMedia",
        "-framework",
        "CoreVideo",
        "-framework",
        "Accelerate",
        "-framework",
        "AppKit",
        "-framework",
        "ImageIO",
    ]
    subprocess.run(cmd, check=True)
    return dest


def resolve_helper(path: Path | None = None, *, build: bool = False, root: Path | None = None) -> Path:
    candidate = path or default_helper_path(root)
    if candidate.is_file():
        return candidate
    if build:
        return build_helper(root)
    raise CaptureError(f"capture helper not found at {candidate}")


def diagnose_permission(helper: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [str(helper), "--permission"],
        check=False,
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        raise CaptureError(proc.stderr.strip() or "permission probe produced no output")
    data = json.loads(proc.stdout)
    if data.get("status") == "denied":
        raise PermissionDenied(data.get("hint") or "Screen Recording denied")
    return data


def list_windows(helper: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [str(helper), "--list-json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise CaptureError(proc.stderr.strip() or proc.stdout)
    return json.loads(proc.stdout)
