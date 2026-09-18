from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from l2_brain.contracts import (
    EncodedVisual,
    MotorIntent,
    Observation,
    PreviousAction,
    SessionHeader,
    StageTimings,
    TelemetryEvent,
    TickRecord,
    ValidityMask,
)
from l2_brain.experiment.frames import should_keep_frame
from l2_brain.experiment.identity import code_identity
from l2_brain.experiment.queues import AsyncWriter
from l2_brain.experiment.timing import TimingAccumulator


class JsonlRecorder:
    def __init__(
        self,
        path: Path | None,
        *,
        bound: int = 128,
        frame_dir: Path | None = None,
        keep_frames: str = "none",
        frame_every: int = 1,
    ) -> None:
        self._path = path
        self._bound = bound
        self._frame_dir = frame_dir
        self._keep_frames = keep_frames
        self._frame_every = frame_every
        self._writer: AsyncWriter | None = None
        self._open = False
        self.rows: list[dict[str, Any]] = []

    def initialize(self, header: SessionHeader | None = None) -> None:
        self._open = True
        self.rows = []
        self._writer = None
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if self._frame_dir is not None:
                self._frame_dir.mkdir(parents=True, exist_ok=True)
            extras = dict(header.extras) if header is not None else {}
            extras.setdefault("code", code_identity())
            self._writer = AsyncWriter(self._path, maxsize=self._bound)
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
        if not self._open:
            raise RuntimeError("JsonlRecorder is closed")
        if (
            image is None
            or self._writer is None
            or self._frame_dir is None
            or not should_keep_frame(tick, self._keep_frames, self._frame_every)
        ):
            return None
        name = f"{tick:06d}.npy"
        dest = self._frame_dir / name
        self._writer.put({"kind": "_frame", "path": str(dest), "image": np.ascontiguousarray(image.copy())})
        return f"{self._frame_dir.name}/{name}"

    def write(self, record: TickRecord) -> None:
        if not self._open:
            raise RuntimeError("JsonlRecorder is closed")
        row = tick_to_json(record)
        self.rows.append(row)
        if self._writer is not None:
            self._writer.put(row)

    @property
    def writer_drops(self) -> int:
        return 0 if self._writer is None else self._writer.dropped

    def close(self) -> None:
        self._open = False
        if self._writer is not None:
            self._writer.close()
            self._writer = None


class CircuitEvaluator:
    def __init__(self) -> None:
        self._open = False
        self._ticks = 0
        self._dropped = 0
        self._pulses = 0
        self._intents = 0
        self._mock_effects = 0
        self._infer: list[float] = []
        self._loop: list[float] = []
        self._timing = TimingAccumulator()
        self._frame_drops = 0
        self._writer_drops = 0

    def initialize(self) -> None:
        self._open = True
        self._ticks = 0
        self._dropped = 0
        self._pulses = 0
        self._intents = 0
        self._mock_effects = 0
        self._infer = []
        self._loop = []
        self._timing = TimingAccumulator()
        self._frame_drops = 0
        self._writer_drops = 0

    def observe(self, record: TickRecord) -> None:
        if not self._open:
            raise RuntimeError("CircuitEvaluator is closed")
        self._ticks += 1
        self._intents += 1
        self._dropped += int(record.command.dropped)
        self._pulses += len(record.command.pulses)
        self._mock_effects += int(record.effect.mock)
        self._infer.append(record.infer_ms)
        self._loop.append(record.loop_ms)
        timings = record.timings
        if timings is not None:
            self._timing.add("wait_frame_ms", timings.wait_frame_ms)
            self._timing.add("frame_age_ms", timings.frame_age_ms)
            self._timing.add("encode_ms", timings.encode_ms)
            self._timing.add("infer_ms", timings.infer_ms)
            self._timing.add("decode_ms", timings.decode_ms)
            self._timing.add("act_ms", timings.act_ms)
            self._timing.add("wait_effect_ms", timings.wait_effect_ms)
        if record.diagnostics:
            self._frame_drops = int(record.diagnostics.get("frame_queue_drops", self._frame_drops))
            self._writer_drops = int(record.diagnostics.get("writer_drops", self._writer_drops))

    def summary(self) -> dict[str, Any]:
        return {
            "ticks": self._ticks,
            "intents": self._intents,
            "dropped": self._dropped,
            "pulses": self._pulses,
            "mock": self._mock_effects == self._ticks and self._ticks > 0,
            "mean_infer_ms": (sum(self._infer) / len(self._infer)) if self._infer else 0.0,
            "mean_loop_ms": (sum(self._loop) / len(self._loop)) if self._loop else 0.0,
            "timing": self._timing.report(),
            "frame_queue_drops": self._frame_drops,
            "writer_drops": self._writer_drops,
        }

    def close(self) -> None:
        self._open = False


def tick_to_json(record: TickRecord) -> dict[str, Any]:
    obs = record.observation
    feat = obs.visual_features
    timings = None if record.timings is None else asdict(record.timings)
    return {
        "kind": "tick",
        "tick": record.tick,
        "frame_id": record.frame_id,
        "observe_ms": record.observe_ms,
        "infer_ms": record.infer_ms,
        "decode_ms": record.decode_ms,
        "act_ms": record.act_ms,
        "loop_ms": record.loop_ms,
        "timings": timings,
        "reward": record.reward,
        "diagnostics": record.diagnostics,
        "frame_ref": record.frame_ref,
        "observation": {
            "timestamp_ns": obs.timestamp_ns,
            "frame_id": obs.frame_id,
            "visual_features": {
                "left": feat.left,
                "center": feat.center,
                "right": feat.right,
                "centroid": feat.centroid,
                "mass": feat.mass,
                "confidence": feat.confidence,
            },
            "target_bearing": obs.target_bearing,
            "target_confidence": obs.target_confidence,
            "motion_estimate": obs.motion_estimate,
            "motion_confidence": obs.motion_confidence,
            "validity_mask": asdict(obs.validity_mask),
            "previous_action": None
            if obs.previous_action is None
            else {
                "turn": obs.previous_action.turn,
                "forward": obs.previous_action.forward,
                "pulses": list(obs.previous_action.pulses),
            },
            "telemetry": [event_to_json(ev) for ev in obs.telemetry],
            "navigation": _navigation_to_json(obs.navigation),
        },
        "intent": {
            "turn": record.intent.turn,
            "forward": record.intent.forward,
            "strafe": record.intent.strafe,
            "stop": record.intent.stop,
            "select_target": record.intent.select_target,
            "attack": record.intent.attack,
            "confidence": record.intent.confidence,
            "valid_until_ns": record.intent.valid_until_ns,
        },
        "command": {
            "turn": record.command.turn,
            "forward": record.command.forward,
            "strafe": record.command.strafe,
            "pulses": list(record.command.pulses),
            "dropped": record.command.dropped,
            "drop_reason": record.command.drop_reason,
            "issued_at_ns": record.command.issued_at_ns,
            "expires_at_ns": record.command.expires_at_ns,
        },
        "effect": {
            "accepted": record.effect.accepted,
            "reason": record.effect.reason,
            "mock": record.effect.mock,
        },
    }


def event_to_json(event: TelemetryEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "timestamp_received_ns": event.timestamp_received_ns,
        "source_timestamp_ns": event.source_timestamp_ns,
        "event_type": event.event_type,
        "actor_id": event.actor_id,
        "target_id": event.target_id,
        "payload": event.payload,
        "confidence": event.confidence,
        "source": event.source,
    }


def event_from_json(data: dict[str, Any]) -> TelemetryEvent:
    return TelemetryEvent(
        event_id=int(data["event_id"]),
        timestamp_received_ns=int(data["timestamp_received_ns"]),
        event_type=str(data["event_type"]),
        payload=dict(data.get("payload") or {}),
        confidence=float(data["confidence"]),
        source=str(data["source"]),
        source_timestamp_ns=data.get("source_timestamp_ns"),
        actor_id=data.get("actor_id"),
        target_id=data.get("target_id"),
    )


def observation_from_json(data: dict[str, Any]) -> Observation:
    feat = data["visual_features"]
    prev = data.get("previous_action")
    mask = data["validity_mask"]
    return Observation(
        timestamp_ns=int(data["timestamp_ns"]),
        frame_id=int(data["frame_id"]),
        visual_features=EncodedVisual(**feat),
        target_bearing=data["target_bearing"],
        target_confidence=float(data["target_confidence"]),
        motion_estimate=data["motion_estimate"],
        motion_confidence=float(data["motion_confidence"]),
        telemetry=tuple(event_from_json(item) for item in data.get("telemetry") or ()),
        validity_mask=_validity_from_json(mask),
        previous_action=None
        if prev is None
        else PreviousAction(turn=prev["turn"], forward=prev["forward"], pulses=tuple(prev["pulses"])),
        navigation=data.get("navigation"),
    )


def _validity_from_json(mask: dict[str, Any]) -> ValidityMask:
    known = {k: mask[k] for k in ValidityMask.__dataclass_fields__ if k in mask}
    return ValidityMask(**known)


def _navigation_to_json(navigation: object | None) -> dict[str, Any] | None:
    if navigation is None:
        return None
    to_dict = getattr(navigation, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(navigation, dict):
        return navigation
    return None


def intent_from_json(data: dict[str, Any]) -> MotorIntent:
    return MotorIntent(
        turn=float(data["turn"]),
        forward=float(data["forward"]),
        strafe=data["strafe"],
        stop=data["stop"],
        select_target=data["select_target"],
        attack=data["attack"],
        confidence=float(data["confidence"]),
        valid_until_ns=int(data["valid_until_ns"]),
    )


def timings_from_json(data: dict[str, Any] | None) -> StageTimings | None:
    if not data:
        return None
    return StageTimings(
        wait_frame_ms=float(data["wait_frame_ms"]),
        frame_age_ms=None if data.get("frame_age_ms") is None else float(data["frame_age_ms"]),
        encode_ms=float(data["encode_ms"]),
        infer_ms=float(data["infer_ms"]),
        decode_ms=float(data["decode_ms"]),
        act_ms=float(data["act_ms"]),
        wait_effect_ms=float(data["wait_effect_ms"]),
        interval_clock=str(data.get("interval_clock", "mono")),
        frame_age_clock=str(data.get("frame_age_clock", "event")),
        infer_synced=bool(data.get("infer_synced", True)),
        infer_is_compute=bool(data.get("infer_is_compute", True)),
    )


def session_jsonl(path: Path) -> Path:
    if path.is_dir():
        return path / "session.jsonl"
    return path


def read_session(path: Path) -> tuple[SessionHeader | None, list[dict[str, Any]]]:
    header = None
    ticks: list[dict[str, Any]] = []
    target = session_jsonl(path)
    for raw in target.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if row.get("kind") == "session_header":
            header = SessionHeader(
                seed=int(row["seed"]),
                ticks_planned=int(row["ticks_planned"]),
                mock=bool(row.get("mock", True)),
                extras=row.get("extras") or {},
            )
        elif row.get("kind") == "tick":
            ticks.append(row)
    return header, ticks


def iter_replay_observations(path: Path) -> Iterator[Observation]:
    _header, ticks = read_session(path)
    for row in ticks:
        yield observation_from_json(row["observation"])
