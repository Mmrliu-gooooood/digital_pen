from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from digital_pen.camera.esp32_client import Esp32CameraClient


def _encode_pgm(image: np.ndarray) -> bytes:
    height, width = image.shape
    return f"P5\n{width} {height}\n255\n".encode("ascii") + image.tobytes()


def _capture_path(base: Path, index: int, count: int) -> Path:
    if count == 1:
        return base
    suffix = base.suffix or ".pgm"
    return base.with_name(f"{base.stem}-{index:06d}{suffix}")


def capture_frames(
    client: Esp32CameraClient,
    output: Path,
    count: int,
) -> list[Path]:
    if count <= 0:
        raise ValueError("count must be positive")

    output.parent.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    previous_frame_id: int | None = None
    expected_shape: tuple[int, int] | None = None
    for index in range(1, count + 1):
        frame = client.capture()
        if previous_frame_id is not None and frame.frame_id <= previous_frame_id:
            raise RuntimeError(
                f"frame IDs are not strictly increasing: "
                f"{previous_frame_id} then {frame.frame_id}"
            )
        if expected_shape is None:
            expected_shape = frame.image.shape
        elif frame.image.shape != expected_shape:
            raise RuntimeError(
                f"frame shape changed from {expected_shape} to {frame.image.shape}"
            )

        path = _capture_path(output, index, count)
        path.write_bytes(_encode_pgm(frame.image))
        paths.append(path)
        previous_frame_id = frame.frame_id
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture raw PGM frames from ESP32")
    parser.add_argument("--url", required=True, help="Device base URL")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    client = Esp32CameraClient(args.url, timeout_s=args.timeout)
    status = client.status()
    print(
        "Device: "
        f"sensor={status.get('sensor')} "
        f"resolution={status.get('resolution')} "
        f"format={status.get('pixel_format')}"
    )
    paths = capture_frames(client, args.output, args.count)
    print(f"Saved {len(paths)} frame(s) to {paths[0].parent.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
