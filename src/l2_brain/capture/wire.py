from __future__ import annotations

import json
import struct
from typing import Any, BinaryIO

MAGIC = b"L2F1"
_HEADER = struct.Struct("<I")


def write_packet(out: BinaryIO, header: dict[str, Any], payload: bytes = b"") -> None:
    raw = json.dumps(header, ensure_ascii=False).encode("utf-8")
    out.write(MAGIC)
    out.write(_HEADER.pack(len(raw)))
    out.write(_HEADER.pack(len(payload)))
    out.write(raw)
    if payload:
        out.write(payload)
    out.flush()


def read_packet(inp: BinaryIO) -> tuple[dict[str, Any], bytes] | None:
    magic = _read_exact(inp, 4)
    if magic is None:
        return None
    if magic != MAGIC:
        raise ValueError(f"bad capture magic {magic!r}")
    header_len = _read_u32(inp)
    payload_len = _read_u32(inp)
    if header_len is None or payload_len is None:
        return None
    header_raw = _read_exact(inp, header_len)
    payload = _read_exact(inp, payload_len) if payload_len else b""
    if header_raw is None or payload is None:
        return None
    header = json.loads(header_raw.decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("capture header must be an object")
    return header, payload


def _read_u32(inp: BinaryIO) -> int | None:
    raw = _read_exact(inp, 4)
    if raw is None:
        return None
    return _HEADER.unpack(raw)[0]


def _read_exact(inp: BinaryIO, n: int) -> bytes | None:
    if n == 0:
        return b""
    chunks = bytearray()
    while len(chunks) < n:
        piece = inp.read(n - len(chunks))
        if not piece:
            return None if not chunks else None
        chunks.extend(piece)
    return bytes(chunks)
