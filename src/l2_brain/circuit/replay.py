from __future__ import annotations

from pathlib import Path

from l2_brain.circuit.policy import FeatureController, PulseDecoder
from l2_brain.circuit.persist import iter_replay_observations
from l2_brain.contracts import Command, MotorIntent
from l2_brain.experiment.identity import OFFLINE_REPLAY_LIMIT


def replay_recorded_observations(
    path: Path,
    *,
    now_ns: int,
    intent_ttl_ns: int = 10**12,
) -> list[tuple[MotorIntent, Command]]:
    """Offline replay of recorded observations. See OFFLINE_REPLAY_LIMIT."""
    controller = FeatureController()
    decoder = PulseDecoder()
    controller.initialize()
    decoder.initialize()
    controller.reset_state()
    out: list[tuple[MotorIntent, Command]] = []
    try:
        for observation in iter_replay_observations(path):
            intent = controller.step(observation, now_ns, intent_ttl_ns)
            command = decoder.decode(intent, now_ns)
            out.append((intent, command))
    finally:
        decoder.close()
        controller.close()
    return out
