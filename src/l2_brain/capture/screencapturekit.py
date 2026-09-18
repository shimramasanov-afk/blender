from __future__ import annotations

from l2_brain.capture.sck import SCKConfig, SCKFrameSource
from l2_brain.types import Observation


class ScreenCaptureKitSource:
    """S0 Observation wrapper. Circuit code should use SCKFrameSource."""

    def __init__(self) -> None:
        self._inner: SCKFrameSource | None = None

    def start(self) -> None:
        raise NotImplementedError(
            "старый Observation-API не подключен. Используйте SCKFrameSource "
            "в контуре Frame. LiveClientEnv по-прежнему закрыт."
        )

    def latest(self) -> Observation:
        raise NotImplementedError("ScreenCaptureKitSource.latest недоступен на Observation-API")

    def stop(self) -> None:
        if self._inner is not None:
            self._inner.close()


__all__ = ["SCKConfig", "SCKFrameSource", "ScreenCaptureKitSource"]
