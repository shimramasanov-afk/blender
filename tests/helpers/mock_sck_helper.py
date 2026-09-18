#!/usr/bin/env python3
"""mock ScreenCaptureKit helper. Speaks the L2F1 stdout protocol."""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from l2_brain.capture.wire import write_packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--width", type=int, default=32)
    parser.add_argument("--height", type=int, default=24)
    parser.add_argument("--resize-at", type=int, default=0)
    parser.add_argument("--lose-at", type=int, default=0)
    parser.add_argument("--sleep-ms", type=float, default=5)
    parser.add_argument("--permission-denied", action="store_true")
    args = parser.parse_args(argv)
    out = sys.stdout.buffer
    if args.permission_denied:
        write_packet(out, {"kind": "permission", "status": "denied", "hint": "denied in mock"})
        return 2
    write_packet(
        out,
        {
            "kind": "hello",
            "window_id": 1,
            "requested_fps": 30,
            "pixel_format": "rgb8",
            "width": args.width,
            "height": args.height,
            "transport": "stdout_pipe",
        },
    )
    width, height = args.width, args.height
    for seq in range(args.frames):
        if args.resize_at and seq == args.resize_at:
            width, height = width + 8, height + 4
            write_packet(out, {"kind": "resize", "width": width, "height": height, "prev_width": args.width, "prev_height": args.height})
        if args.lose_at and seq == args.lose_at:
            write_packet(out, {"kind": "source_lost", "reason": "mock window gone"})
            return 0
        image = np.zeros((height, width, 3), dtype=np.uint8)
        image[:] = (70, 72, 80)
        image[4:12, 4:12] = (220, 36, 36)
        payload = image.tobytes()
        write_packet(
            out,
            {
                "kind": "frame",
                "width": width,
                "height": height,
                "pixel_format": "rgb8",
                "stride": width * 3,
                "seq": seq,
                "window_id": 1,
                "host_unix_ns": time.time_ns(),
                "sck_pts_ns": seq * 1_000_000,
                "sck_pts_clock": "cmtime",
                "copy_ms": 0.1,
                "copies": 1,
                "bytes": len(payload),
                "drops": 0,
                "source_id": "mock.sck",
            },
            payload,
        )
        time.sleep(args.sleep_ms / 1000.0)
    write_packet(out, {"kind": "stats", "frames": args.frames, "drops": 0, "transport": "stdout_pipe"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
