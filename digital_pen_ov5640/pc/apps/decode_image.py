from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from digital_pen.anoto import (
    DIRECTION_VECTORS,
    AnotoDecodeError,
    build_direction_matrices,
    decode_oriented_consensus,
)
from digital_pen.vision import (
    DotDetectorConfig,
    classify_grid_fit,
    detect_dots,
    fit_grid,
    project_points,
)


def _load_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        if path.suffix.lower() == ".json":
            loaded = json.load(stream)
        else:
            loaded = yaml.safe_load(stream)
    if not isinstance(loaded, dict):
        raise ValueError("pattern configuration must contain a mapping")
    return loaded


def _pattern_identity(
    path: Path,
    profile_name: str,
    section_override: tuple[int, int] | None,
) -> tuple[str, tuple[int, int], tuple[int, int] | None]:
    config = _load_mapping(path)
    if "profiles" in config:
        profiles = config["profiles"]
        if not isinstance(profiles, dict) or profile_name not in profiles:
            raise ValueError(f"pattern profile {profile_name!r} was not found")
        profile = profiles[profile_name]
        if not isinstance(profile, dict):
            raise ValueError("selected pattern profile must contain a mapping")
    else:
        profile = config
    manifest_value = profile.get("manifest")
    if manifest_value is not None:
        manifest_path = (path.parent / str(manifest_value)).resolve()
        profile = _load_mapping(manifest_path)
    page_id = str(profile["page_id"])
    if section_override is not None:
        section = section_override
    elif "section_u" in profile and "section_v" in profile:
        section = (int(profile["section_u"]), int(profile["section_v"]))
    else:
        raise ValueError(
            "pattern YAML has no section; pass --section-u and --section-v "
            "or use a manifest JSON"
        )
    bounds = None
    if "cols" in profile and "rows" in profile:
        bounds = (int(profile["cols"]), int(profile["rows"]))
    return page_id, section, bounds


def _render_annotation(
    gray: np.ndarray,
    fit,
    classified,
    summary: str,
) -> np.ndarray:
    annotated = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    grid_centers = project_points(
        np.asarray([(item.col, item.row) for item in classified], dtype=np.float64),
        fit.model.grid_to_image,
    )
    arrow_length = max(4.0, fit.model.spacing_px * 0.28)
    for center, item in zip(grid_centers, classified, strict=True):
        dx, dy = DIRECTION_VECTORS[item.direction]
        start = tuple(int(round(value)) for value in center)
        end = (
            int(round(center[0] + dx * arrow_length)),
            int(round(center[1] + dy * arrow_length)),
        )
        cv2.circle(annotated, start, 2, (0, 220, 0), -1)
        cv2.arrowedLine(annotated, start, end, (0, 128, 255), 1, tipLength=0.4)
    cv2.rectangle(annotated, (0, 0), (annotated.shape[1] - 1, 24), (0, 0, 0), -1)
    cv2.putText(
        annotated,
        summary,
        (5, 17),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return annotated


def _write_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise OSError(f"could not write annotated image: {path}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decode an Anoto coordinate from one grayscale image"
    )
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--pattern", type=Path, required=True)
    parser.add_argument("--profile", default="A")
    parser.add_argument("--section-u", type=int)
    parser.add_argument("--section-v", type=int)
    parser.add_argument("--annotated", type=Path, required=True)
    parser.add_argument("--min-area", type=float, default=1.0)
    parser.add_argument("--max-area", type=float, default=100.0)
    parser.add_argument("--min-aspect-ratio", type=float, default=0.2)
    parser.add_argument("--min-circularity", type=float, default=0.1)
    parser.add_argument("--adaptive-block-size", type=int, default=11)
    parser.add_argument("--adaptive-c", type=float, default=6.0)
    parser.add_argument("--direction-confidence", type=float, default=0.75)
    parser.add_argument("--min-windows", type=int, default=2)
    parser.add_argument("--max-missing-directions", type=int, default=1)
    parser.add_argument("--disable-mirror-search", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if (args.section_u is None) != (args.section_v is None):
        raise ValueError("--section-u and --section-v must be provided together")
    section_override = (
        None
        if args.section_u is None
        else (int(args.section_u), int(args.section_v))
    )
    page_id, section, position_bounds = _pattern_identity(
        args.pattern.resolve(), args.profile, section_override
    )
    gray = cv2.imread(str(args.image), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise FileNotFoundError(f"could not read grayscale image: {args.image}")

    detector_config = DotDetectorConfig(
        min_area_px=args.min_area,
        max_area_px=args.max_area,
        min_aspect_ratio=args.min_aspect_ratio,
        min_circularity=args.min_circularity,
        threshold_method="adaptive",
        adaptive_block_size=args.adaptive_block_size,
        adaptive_c=args.adaptive_c,
        morphology_enabled=False,
    )
    observations, _ = detect_dots(gray, detector_config)
    fit = fit_grid(observations)
    classified = classify_grid_fit(
        observations,
        fit,
        min_offset=0.08,
    )
    directions, confidences = build_direction_matrices(classified)
    # Images have a top-left, downward-positive row axis; generator matrices
    # use PDF's upward-positive row convention. This is a coordinate-system
    # conversion, so direction labels themselves remain unchanged here.
    directions = np.flipud(directions)
    confidences = np.flipud(confidences)
    result = decode_oriented_consensus(
        directions,
        confidences,
        section=section,
        page_id=page_id,
        timestamp_us=args.image.stat().st_mtime_ns // 1_000,
        min_direction_confidence=args.direction_confidence,
        min_supporting_windows=args.min_windows,
        max_missing_directions=args.max_missing_directions,
        position_bounds=position_bounds,
        allow_mirror=not args.disable_mirror_search,
    )
    pose = result.pose
    summary = (
        f"{pose.page_id} ({pose.x_grid:.0f},{pose.y_grid:.0f}) "
        f"windows={result.supporting_windows}/{result.decoded_windows} "
        f"confidence={pose.confidence:.3f}"
    )
    _write_image(args.annotated, _render_annotation(gray, fit, classified, summary))
    print(f"page: {pose.page_id}")
    print(f"grid: ({pose.x_grid:.0f}, {pose.y_grid:.0f})")
    print(
        "valid windows: "
        f"{result.supporting_windows}/{result.decoded_windows} "
        f"({result.candidate_windows} candidates)"
    )
    print(f"confidence: {pose.confidence:.6f}")
    print(f"rotation quadrants: {pose.rotation_quadrants}")
    print(f"mirrored: {str(result.mirrored).lower()}")
    print(f"annotated: {args.annotated.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AnotoDecodeError as error:
        print(f"decode failed: {error}")
        raise SystemExit(2) from error
