from __future__ import annotations

from l2_brain.safety import LIVE_CLIENT_BLOCKED_REASON
from l2_brain.types import Action


class LiveHIDActuator:
    def apply(self, action: Action) -> None:
        raise NotImplementedError(
            "Живой ввод закрыт до этапа S3. Безопасное окно, не клиент. "
            + LIVE_CLIENT_BLOCKED_REASON
        )

    def emergency_stop(self) -> None:
        return None
