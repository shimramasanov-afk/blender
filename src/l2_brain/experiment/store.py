from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from l2_brain.circuit.config import CircuitConfig
from l2_brain.circuit.persist import JsonlRecorder, tick_to_json
from l2_brain.contracts import SessionHeader, TickRecord
from l2_brain.experiment.frames import should_keep_frame
from l2_brain.experiment.identity import OFFLINE_REPLAY_LIMIT, code_identity, public_circuit_config
from l2_brain.experiment.queues import AsyncWriter


class ExperimentStore:
    """Directory session: manifest, async JSONL, optional frame sidecars."""

    def __init__(
        self,
        root: Path,
        *,
        keep_frames: str = "all",
        frame_every: int = 1,
        writer_bound: int = 128,
        model_version: str = "unknown",
        config: CircuitConfig | None = None,
    ) -> None:
        self.root = root
        self.keep_frames = keep_frames
        self.frame_every = frame_every
        self.writer_bound = writer_bound
        self.model_version = model_version
        self.config = config
        self.rows: list[dict[str, Any]] = []
        self._writer: AsyncWriter | None = None
        self._open = False
        self._frame_dir = root / "frames"

    def initialize(self, header: SessionHeader | None = None) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._frame_dir.mkdir(parents=True, exist_ok=True)
        self._writer = AsyncWriter(self.root / "session.jsonl", maxsize=self.writer_bound)
        self._open = True
        self.rows = []
        extras = dict(header.extras) if header is not None else {}
        extras.update(
            {
                "code": code_identity(),
                "model_version": self.model_version,
                "clocks": {
                    "intervals": "mono",
                    "events": "event",
                    "mixing": "forbidden_without_explicit_offset",
                },
                "offline_replay_limitation": OFFLINE_REPLAY_LIMIT,
                "config": public_circuit_config(self.config) if self.config is not None else {},
            }
        )
        manifest = {
            "schema": "l2-experiment-v1",
            "seed": header.seed if header else None,
            "ticks_planned": header.ticks_planned if header else None,
            "mock": header.mock if header else True,
            "extras": extras,
        }
        (self.root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if header is not None:
            self._writer.put(
                {
                    "kind": "session_header",
                    "seed": header.seed,
                    "ticks_planned": header.ticks_planned,
                    "mock": header.mock,
                    "extras": extras,
                }
            )

    def store_frame(self, tick: int, image: np.ndarray | None) -> str | None:
        if not self._open or self._writer is None:
            raise RuntimeError("ExperimentStore is closed")
        if image is None or not should_keep_frame(tick, self.keep_frames, self.frame_every):
            return None
        rel = f"frames/{tick:06d}.npy"
        self._writer.put({"kind": "_frame", "path": str(self.root / rel), "image": np.ascontiguousarray(image.copy())})
        return rel

    def write(self, record: TickRecord) -> None:
        if not self._open or self._writer is None:
            raise RuntimeError("ExperimentStore is closed")
        row = tick_to_json(record)
        self.rows.append(row)
        self._writer.put(row)

    @property
    def writer_drops(self) -> int:
        return 0 if self._writer is None else self._writer.dropped

    def close(self) -> None:
        self._open = False
        if self._writer is not None:
            self._writer.close()
            self._writer = None


def build_recorder(config: CircuitConfig) -> JsonlRecorder | ExperimentStore:
    path = config.record_path
    if path is None:
        return JsonlRecorder(None)
    if path.suffix == ".jsonl":
        frame_dir = path.with_name(path.stem + "_frames") if config.keep_frames != "none" else None
        return JsonlRecorder(
            path,
            bound=config.writer_bound,
            frame_dir=frame_dir,
            keep_frames=config.keep_frames,
            frame_every=config.frame_every,
        )
    return ExperimentStore(
        path,
        keep_frames=config.keep_frames,
        frame_every=config.frame_every,
        writer_bound=config.writer_bound,
        model_version=config.model_version,
        config=config,
    )
