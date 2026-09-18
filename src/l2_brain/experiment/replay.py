from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from l2_brain.circuit.persist import read_session, session_jsonl as _session_jsonl
from l2_brain.experiment.identity import OFFLINE_REPLAY_LIMIT

PLAY_MODES = ("offline", "realtime", "speed", "step")


@dataclass(frozen=True, slots=True)
class TickView:
    tick: int
    frame_id: int
    frame_image: np.ndarray | None
    frame_ref: str | None
    frame_sha256: str | None
    timestamps: dict[str, Any]
    features: dict[str, Any]
    telemetry: list[dict[str, Any]]
    intent: dict[str, Any]
    command: dict[str, Any]
    reward: float | None
    diagnostics: dict[str, Any]
    timings: dict[str, Any]
    effect: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        image = None
        if self.frame_image is not None:
            image = {
                "shape": list(self.frame_image.shape),
                "dtype": str(self.frame_image.dtype),
                "sha256": self.frame_sha256,
                "ref": self.frame_ref,
            }
        return {
            "tick": self.tick,
            "frame_id": self.frame_id,
            "frame": image,
            "timestamps": self.timestamps,
            "features": self.features,
            "telemetry": self.telemetry,
            "intent": self.intent,
            "command": self.command,
            "reward": self.reward,
            "diagnostics": self.diagnostics,
            "timings": self.timings,
            "effect": self.effect,
            "offline_replay_limitation": OFFLINE_REPLAY_LIMIT,
        }


class SessionReplay:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.root = path if path.is_dir() else path.parent
        self.header, self.ticks = read_session(_session_jsonl(path))
        self._index = 0

    def __len__(self) -> int:
        return len(self.ticks)

    def inspect(self, tick: int) -> TickView:
        if tick < 0 or tick >= len(self.ticks):
            raise IndexError(f"tick {tick} not in 0..{len(self.ticks) - 1}")
        row = self.ticks[tick]
        obs = row["observation"]
        frame_ref = row.get("frame_ref")
        image = _load_frame(self.root, frame_ref)
        digest = None
        if image is not None:
            digest = hashlib.sha256(np.ascontiguousarray(image).tobytes()).hexdigest()
        return TickView(
            tick=int(row["tick"]),
            frame_id=int(row["frame_id"]),
            frame_image=image,
            frame_ref=frame_ref,
            frame_sha256=digest,
            timestamps={
                "observation_ns": obs.get("timestamp_ns"),
                "command_issued_ns": row.get("command", {}).get("issued_at_ns"),
                "clock": "event",
            },
            features=obs.get("visual_features") or {},
            telemetry=list(obs.get("telemetry") or []),
            intent=row.get("intent") or {},
            command=row.get("command") or {},
            reward=row.get("reward"),
            diagnostics=row.get("diagnostics") or {},
            timings=row.get("timings") or {},
            effect=row.get("effect") or {},
        )

    def step(self) -> TickView:
        view = self.inspect(self._index)
        self._index += 1
        return view

    def reset_cursor(self) -> None:
        self._index = 0

    def remaining(self) -> bool:
        return self._index < len(self.ticks)

    def play(
        self,
        *,
        speed: float = 1.0,
        sleep: bool = True,
        mode: str = "realtime",
    ) -> Iterator[TickView]:
        if mode not in PLAY_MODES:
            raise ValueError(f"unknown play mode {mode!r}")
        if mode == "offline":
            raise ValueError("use replay_recorded_observations for offline controller compare")
        if mode == "step":
            sleep = False
        prev_ns: int | None = None
        for idx in range(len(self.ticks)):
            view = self.inspect(idx)
            now_ns = view.timestamps.get("observation_ns")
            if sleep and prev_ns is not None and now_ns is not None:
                _sleep_event_delta(int(now_ns) - int(prev_ns), speed)
            if now_ns is not None:
                prev_ns = int(now_ns)
            yield view

    def limitation(self) -> str:
        return OFFLINE_REPLAY_LIMIT


def _sleep_event_delta(delta_ns: int, speed: float) -> None:
    if speed <= 0 or delta_ns <= 0:
        return
    time.sleep((delta_ns / 1_000_000_000.0) / speed)


def _load_frame(root: Path, frame_ref: str | None) -> np.ndarray | None:
    if not frame_ref:
        return None
    path = Path(frame_ref)
    if not path.is_absolute():
        path = root / frame_ref
    if not path.is_file():
        return None
    loaded = np.load(path)
    return np.asarray(loaded)


def write_timing_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
