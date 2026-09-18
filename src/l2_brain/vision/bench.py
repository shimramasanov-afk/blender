from __future__ import annotations

from typing import Any

import numpy as np

from l2_brain.contracts import Frame
from l2_brain.experiment.clocks import mono_ns
from l2_brain.vision.channels import NavigationChannels
from l2_brain.vision.config import CANDIDATES, VisionConfig
from l2_brain.vision.encoder import NavigationEncoder


def make_frame(image: np.ndarray, frame_id: int) -> Frame:
    return Frame(
        frame_id=frame_id,
        timestamp_capture_ns=1_000_000_000 + frame_id * 50_000_000,
        timestamp_received_ns=1_000_000_000 + frame_id * 50_000_000,
        width=image.shape[1],
        height=image.shape[0],
        pixel_format="rgb8",
        source_id="vision.synth",
        image=image,
        clock_id="event",
    )


def checker(height: int = 64, width: int = 80, cell: int = 5, light: float = 1.0, seed: int = 0) -> np.ndarray:
    yy, xx = np.indices((height, width))
    flag = ((xx // cell) + (yy // cell)) % 2
    base = np.where(flag, 210, 46).astype(np.float32) * light
    noise = np.random.default_rng(seed).integers(-18, 19, (height, width), dtype=np.int16)
    low = 26.0 * np.sin(xx * 0.19 + 0.3) + 20.0 * np.sin(yy * 0.15)
    base = np.clip(base + noise + low, 0, 255)
    rgb = np.stack([base, base * 0.95, base * 0.85], axis=2)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def shift(image: np.ndarray, dx: int) -> np.ndarray:
    return np.roll(image, dx, axis=1)


def zoom(image: np.ndarray, factor: float) -> np.ndarray:
    height, width = image.shape[:2]
    nh, nw = max(8, int(height / factor)), max(8, int(width / factor))
    y0, x0 = (height - nh) // 2, (width - nw) // 2
    crop = image[y0 : y0 + nh, x0 : x0 + nw]
    ys = np.linspace(0, crop.shape[0] - 1, height).astype(np.int32)
    xs = np.linspace(0, crop.shape[1] - 1, width).astype(np.int32)
    return np.ascontiguousarray(crop[ys][:, xs])


def encode_pair(
    first: np.ndarray,
    second: np.ndarray,
    config: VisionConfig | None = None,
    *,
    stale: bool = False,
) -> NavigationChannels:
    enc = NavigationEncoder(config)
    enc.initialize()
    enc.encode(make_frame(first, 1), (), None, 10, False)
    obs = enc.encode(make_frame(second, 2), (), None, 20, stale)
    enc.close()
    assert obs.navigation is not None
    return obs.navigation  # type: ignore[return-value]


def discrimination_score(config: VisionConfig) -> dict[str, Any]:
    rows = []
    for dx in (3, 4, 5):
        ch = encode_pair(checker(), shift(checker(), dx), config)
        rows.append(("camera_turn", ch.hypothesis.label, ch))
    for factor in (1.10, 1.14, 1.18):
        ch = encode_pair(checker(), zoom(checker(), factor), config)
        rows.append(("approach", ch.hypothesis.label, ch))
    correct = sum(1 for expected, label, _ in rows if label == expected)
    low = sum(1 for _e, label, _ in rows if label == "low_confidence")
    return {
        "n": len(rows),
        "correct": correct,
        "accuracy": correct / len(rows),
        "low_confidence": low,
        "labels": [(e, lab) for e, lab, _ in rows],
    }


def measure_configs(repeats: int = 8) -> list[dict[str, Any]]:
    image = checker()
    out = []
    for config in CANDIDATES:
        times = []
        enc = NavigationEncoder(config)
        enc.initialize()
        enc.encode(make_frame(image, 1), (), None, 1, False)
        for i in range(repeats):
            moved = shift(image, 2 + (i % 4)) if i % 2 == 0 else zoom(image, 1.10 + 0.02 * (i % 3))
            t0 = mono_ns()
            enc.encode(make_frame(moved, i + 2), (), None, i + 2, False)
            times.append((mono_ns() - t0) / 1_000_000.0)
        enc.close()
        disc = discrimination_score(config)
        sim = sim_separation(config)
        out.append(
            {
                "width": config.width,
                "height": config.height,
                "sectors": f"{config.sectors_x}x{config.sectors_y}",
                "flow": f"{config.flow_nx}x{config.flow_ny}",
                "encode_ms_p50": float(np.median(times)),
                "encode_ms_p95": float(np.percentile(times, 95)),
                "n": len(times),
                "accuracy": disc["accuracy"],
                "correct": disc["correct"],
                "pairs": disc["n"],
                "sim_separates": sim,
            }
        )
    return out


def sim_separation(config: VisionConfig) -> bool:
    """True when a sim turn and a sim approach get different visual labels."""
    from l2_brain.sim.config import EpisodeSpec, SimConfig
    from l2_brain.sim.environment import SimulationEnvironment, forward_intent, turn_intent

    def once(scenario: str, intent_fn, steps: int, **extra: object) -> NavigationChannels:
        spec = EpisodeSpec(
            scenario=scenario,
            split="training",
            variant=0,
            seed=0,
            config=SimConfig(frame_w=64, frame_h=64, **{"max_steps": 20, **extra}),  # type: ignore[arg-type]
        )
        env = SimulationEnvironment(spec)
        env.initialize()
        view = env.reset_episode()
        enc = NavigationEncoder(config)
        enc.initialize()
        obs = enc.encode(make_frame(view.frame.image, 1), (), None, 1, False)
        for i in range(steps):
            view, _gt = env.step(intent_fn())
            obs = enc.encode(make_frame(view.frame.image, i + 2), (), obs, i + 2, False)
        env.close()
        enc.close()
        assert obs.navigation is not None
        return obs.navigation  # type: ignore[return-value]

    turn = once("camera_spin", lambda: turn_intent(1.0), 2)
    approach = once("single_obstacle", lambda: forward_intent(), 2, start_xy=(5.2, 8.0), start_yaw=0.0)
    different = turn.hypothesis.label != approach.hypothesis.label
    signed = approach.expansion > turn.expansion + 0.02 or (
        turn.hypothesis.label == "camera_turn" and approach.hypothesis.label == "approach"
    )
    return bool(different and signed)


def pick_starter(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Smallest config that is accurate on transforms and separates sim approach vs turn."""
    usable = [row for row in rows if row["accuracy"] >= 0.8 and row.get("sim_separates")]
    pool = usable or [row for row in rows if row["accuracy"] >= 0.8] or rows
    return min(pool, key=lambda row: (row["width"] * row["height"], row["encode_ms_p50"]))
