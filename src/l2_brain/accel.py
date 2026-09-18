"""Compute backend. MPS/Metal stay off until H6 is measured."""

BACKEND = "numpy_cpu"


def selected_backend() -> str:
    return BACKEND
