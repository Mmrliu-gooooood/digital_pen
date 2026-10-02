from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np

from digital_pen.vision import (
    DotDetectionResult,
    DotDetectorConfig,
    RejectionReason,
    analyze_dots,
)


def render_annotation(gray: np.ndarray, result: DotDetectionResult) -> np.ndarray:
    """Overlay accepted dots and rejected, potentially missed candidates."""
    annotated = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for candidate in result.candidates:
        x, y, width, height = candidate.bounding_box
        if candidate.accepted:
            color = (0, 200, 0)
        elif candidate.rejection_reason in {
            RejectionReason.AREA_TOO_SMALL,
            RejectionReason.AREA_TOO_LARGE,
        }:
            color = (0, 165, 255)
        else:
            color = (0, 0, 255)
        cv2.rectangle(
            annotated,
            (x, y),
            (x + width - 1, y + height - 1),
            color,
            1,
        )
        center = tuple(round(value) for value in candidate.center_px)
        cv2.drawMarker(
            annotated,
            center,
            color,
            markerType=cv2.MARKER_CROSS,
            markerSize=7,
            thickness=1,
        )
        if not candidate.accepted and candidate.rejection_reason is not None:
            cv2.putText(
                annotated,
                candidate.rejection_reason.value,
                (x, max(9, y - 2)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.25,
                color,
                1,
                cv2.LINE_AA,
            )
    return annotated


def _write_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise OSError(f"could not write image: {path}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect and annotate monochrome Anoto dot candidates"
    )
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--annotated", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--stages-dir", type=Path)
    parser.add_argument("--min-area", type=float, default=3.0)
    parser.add_argument("--max-area", type=float, default=200.0)
    parser.add_argument("--min-aspect-ratio", type=float, default=0.5)
    parser.add_argument("--min-circularity", type=float, default=0.5)
    parser.add_argument(
        "--threshold-method", choices=("otsu", "adaptive"), default="otsu"
    )
    parser.add_argument("--disable-threshold", action="store_true")
    parser.add_argument("--adaptive-block-size", type=int, default=31)
    parser.add_argument("--adaptive-c", type=float, default=5.0)
    parser.add_argument("--enable-clahe", action="store_true")
    parser.add_argument("--clahe-clip-limit", type=float, default=2.0)
    parser.add_argument("--disable-morphology", action="store_true")
    parser.add_argument("--morphology-kernel-size", type=int, default=3)
    parser.add_argument("--morphology-iterations", type=int, default=1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    gray = cv2.imread(str(args.image), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise FileNotFoundError(f"could not read grayscale image: {args.image}")

    config = DotDetectorConfig(
        min_area_px=args.min_area,
        max_area_px=args.max_area,
        min_aspect_ratio=args.min_aspect_ratio,
        min_circularity=args.min_circularity,
        clahe_enabled=args.enable_clahe,
        clahe_clip_limit=args.clahe_clip_limit,
        threshold_enabled=not args.disable_threshold,
        threshold_method=args.threshold_method,
        adaptive_block_size=args.adaptive_block_size,
        adaptive_c=args.adaptive_c,
        morphology_enabled=not args.disable_morphology,
        morphology_kernel_size=args.morphology_kernel_size,
        morphology_iterations=args.morphology_iterations,
    )
    result = analyze_dots(gray, config)
    _write_image(args.annotated, render_annotation(gray, result))
    if args.binary is not None:
        _write_image(args.binary, result.binary)
    if args.stages_dir is not None:
        for name, image in result.stages.items():
            _write_image(args.stages_dir / f"{name}.png", image)

    rejection_counts = Counter(
        candidate.rejection_reason
        for candidate in result.candidates
        if not candidate.accepted
    )
    summary = ", ".join(
        f"{reason.value}={count}"
        for reason, count in sorted(rejection_counts.items(), key=lambda item: item[0])
    )
    print(
        f"accepted={len(result.observations)} "
        f"suspicious={sum(rejection_counts.values())}"
        + (f" ({summary})" if summary else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
