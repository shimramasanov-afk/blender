from __future__ import annotations

from l2_brain.contracts import Command, MotorIntent, Observation, PreviousAction


class FeatureController:
    """Reactive policy on encoded features. Short memory is side; weights are gain."""

    name = "feature_reactive"

    def __init__(self) -> None:
        self._default_gain = 3.2
        self._gain = self._default_gain
        self._side = 0.0
        self._open = False

    def initialize(self) -> None:
        self._open = True
        self.reset_state()

    def reset_state(self) -> None:
        self._side = 0.0

    def reset_weights(self) -> None:
        self._gain = self._default_gain

    def step(self, observation: Observation, now_ns: int, intent_ttl_ns: int) -> MotorIntent:
        if not self._open:
            raise RuntimeError("FeatureController is closed")
        until = now_ns + intent_ttl_ns
        if observation.validity_mask.stale or not observation.validity_mask.frame:
            return MotorIntent(
                turn=0.0,
                forward=0.0,
                strafe=None,
                stop="fire",
                select_target="idle",
                attack="idle",
                confidence=0.0,
                valid_until_ns=until,
            ).clipped()
        feat = observation.visual_features
        seen = observation.validity_mask.target and feat.centroid is not None
        if seen and feat.centroid is not None:
            offset = feat.centroid - 0.5
            if abs(offset) > 0.07:
                self._side = 1.0 if offset > 0 else -1.0
            if feat.mass > 0.045 and abs(offset) < 0.08:
                return MotorIntent(
                    turn=0.0,
                    forward=0.15,
                    strafe=None,
                    stop="idle",
                    select_target="fire",
                    attack="fire",
                    confidence=feat.confidence,
                    valid_until_ns=until,
                ).clipped()
            if abs(offset) < 0.06:
                return MotorIntent(
                    turn=0.0,
                    forward=1.0,
                    strafe=None,
                    stop="idle",
                    select_target="idle",
                    attack="idle",
                    confidence=feat.confidence,
                    valid_until_ns=until,
                ).clipped()
            return MotorIntent(
                turn=offset * self._gain,
                forward=0.25,
                strafe=None,
                stop="idle",
                select_target="idle",
                attack="idle",
                confidence=feat.confidence,
                valid_until_ns=until,
            ).clipped()
        turn = 0.55 * self._side if self._side != 0.0 else 0.35
        return MotorIntent(
            turn=turn,
            forward=0.0,
            strafe=None,
            stop="idle",
            select_target="idle",
            attack="idle",
            confidence=0.2 if self._side != 0.0 else 0.1,
            valid_until_ns=until,
        ).clipped()

    def close(self) -> None:
        self._open = False


class PulseDecoder:
    def __init__(self, *, strafe_supported: bool = False) -> None:
        self._strafe = strafe_supported
        self._open = False

    def initialize(self) -> None:
        self._open = True

    def decode(self, intent: MotorIntent, now_ns: int) -> Command:
        if not self._open:
            raise RuntimeError("PulseDecoder is closed")
        intent = intent.clipped()
        if now_ns > intent.valid_until_ns:
            return Command(
                turn=0.0,
                forward=0.0,
                strafe=None,
                pulses=("stop",),
                issued_at_ns=now_ns,
                expires_at_ns=now_ns,
                dropped=True,
                drop_reason="intent_expired",
            )
        strafe = intent.strafe if self._strafe else None
        return Command(
            turn=intent.turn,
            forward=intent.forward,
            strafe=strafe,
            pulses=intent.pulses,
            issued_at_ns=now_ns,
            expires_at_ns=intent.valid_until_ns,
            dropped=False,
        )

    def close(self) -> None:
        self._open = False


def attach_previous(observation: Observation, command: Command) -> Observation:
    return Observation(
        timestamp_ns=observation.timestamp_ns,
        frame_id=observation.frame_id,
        visual_features=observation.visual_features,
        target_bearing=observation.target_bearing,
        target_confidence=observation.target_confidence,
        motion_estimate=observation.motion_estimate,
        motion_confidence=observation.motion_confidence,
        telemetry=observation.telemetry,
        validity_mask=observation.validity_mask,
        previous_action=PreviousAction(
            turn=command.turn,
            forward=command.forward,
            pulses=command.pulses,
        ),
        navigation=observation.navigation,
    )
