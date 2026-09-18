from __future__ import annotations


class CaptureError(RuntimeError):
    pass


class PermissionDenied(CaptureError):
    pass


class SourceLost(CaptureError):
    pass
