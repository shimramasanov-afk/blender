from __future__ import annotations

from l2_brain.circuit.encode import ColorBlobEncoder
from l2_brain.circuit.loop import build_mock_circuit
from l2_brain.circuit.config import CircuitConfig
from l2_brain.factory import build_encoder
from l2_brain.vision.encoder import NavigationEncoder


def test_factory_names() -> None:
    assert isinstance(build_encoder("color_blob"), ColorBlobEncoder)
    assert isinstance(build_encoder("navigation_v1"), NavigationEncoder)


def test_mock_reports_color_blob() -> None:
    circuit = build_mock_circuit(CircuitConfig(ticks=2, encoder_name="color_blob"))
    assert type(circuit.encoder).__name__ == "ColorBlobEncoder"
    circuit.close()
