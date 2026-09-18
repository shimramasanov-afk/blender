from __future__ import annotations

import numpy as np

from l2_brain.circuit.config import CircuitConfig
from l2_brain.contracts import Command, Effect, Frame, TelemetryEvent
from l2_brain.experiment.queues import LatestOnlyQueue, QueueEmpty


class MockFrameSource:
    """Bounded last-frame queue. Artificial RGB with a red blob. mock=true."""

    def __init__(self, config: CircuitConfig) -> None:
        self._config = config
        self._open = False
        self._rng = np.random.default_rng(config.seed)
        self._inbox: LatestOnlyQueue[Frame] = LatestOnlyQueue()
        self._next_id = 1

    def initialize(self) -> None:
        self._open = True
        self.reset_episode(self._config.seed)

    def reset_episode(self, seed: int | None = None) -> None:
        self._rng = np.random.default_rng(self._config.seed if seed is None else seed)
        self._inbox = LatestOnlyQueue()
        self._next_id = 1

    def latest(self) -> Frame:
        if not self._open:
            raise RuntimeError("MockFrameSource is closed")
        try:
            return self._inbox.take()
        except QueueEmpty:
            frame = self._render()
            self._inbox.put(frame)
            return self._inbox.take()

    def inject(self, frame: Frame) -> None:
        self._inbox.put(frame)

    @property
    def queue_drops(self) -> int:
        return self._inbox.drops

    def close(self) -> None:
        self._open = False
        self._inbox = LatestOnlyQueue()

    def _render(self) -> Frame:
        cfg = self._config
        image = np.zeros((cfg.frame_h, cfg.frame_w, 3), dtype=np.uint8)
        image[:] = (70, 72, 80)
        # Blob walks slowly so encoder can estimate motion; no privileged pose.
        t = self._next_id - 1
        cx = int(cfg.frame_w * (0.28 + 0.012 * (t % 12)))
        cy = cfg.frame_h // 2
        x0, x1 = max(2, cx - 6), min(cfg.frame_w - 2, cx + 6)
        y0, y1 = max(2, cy - 8), min(cfg.frame_h - 2, cy + 8)
        image[y0:y1, x0:x1] = (220, 36, 36)
        now = _now(cfg)
        frame = Frame(
            frame_id=self._next_id,
            timestamp_capture_ns=now - 1_000_000,
            timestamp_received_ns=now,
            width=cfg.frame_w,
            height=cfg.frame_h,
            pixel_format="rgb8",
            source_id=cfg.source_id,
            image=image,
        )
        self._next_id += 1
        return frame


class MockTelemetrySource:
    def __init__(self) -> None:
        self._open = False
        self._n = 0

    def initialize(self) -> None:
        self._open = True
        self._n = 0

    def reset_episode(self, seed: int | None = None) -> None:
        self._n = 0

    def poll(self) -> tuple[TelemetryEvent, ...]:
        if not self._open:
            raise RuntimeError("MockTelemetrySource is closed")
        from l2_brain.experiment.clocks import event_ns

        self._n += 1
        return (
            TelemetryEvent(
                event_id=self._n,
                timestamp_received_ns=event_ns(),
                event_type="mock.heartbeat",
                payload={"seq": self._n},
                confidence=1.0,
                source="mock.telemetry",
            ),
        )

    def close(self) -> None:
        self._open = False


class MockInputBackend:
    def __init__(self) -> None:
        self._open = False
        self.last: Command | None = None
        self.held: tuple[str, ...] = ()
        self.applied: list[Command] = []

    def initialize(self) -> None:
        self._open = True
        self.reset_episode(None)

    def reset_episode(self, seed: int | None = None) -> None:
        self.last = None
        self.held = ()
        self.applied = []

    def apply(self, command: Command) -> Effect:
        if not self._open:
            raise RuntimeError("MockInputBackend is closed")
        if command.dropped:
            self.held = ()
            return Effect(accepted=False, reason=command.drop_reason or "dropped", mock=True)
        self.last = command
        self.applied.append(command)
        if "stop" in command.pulses:
            self.held = ()
        # Pulses are not latched. Continuous axes are the only hold.
        self.held = ()
        return Effect(accepted=True, reason="mock.apply", mock=True)

    def wait_observed_effect(self, effect: Effect) -> Effect:
        return effect

    def emergency_stop(self) -> None:
        self.held = ()
        self.last = Command(
            turn=0.0,
            forward=0.0,
            strafe=None,
            pulses=("stop",),
            issued_at_ns=0,
            expires_at_ns=0,
            dropped=False,
            drop_reason=None,
        )

    def close(self) -> None:
        self.emergency_stop()
        self._open = False


def _now(config: CircuitConfig) -> int:
    if config.now_ns is not None:
        return int(config.now_ns())
    import time

    return time.time_ns()
