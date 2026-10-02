"""Sliding-window Anoto decoding with confidence-weighted consensus."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from math import exp

import numpy as np

from digital_pen.anoto.codec_adapter import (
    DIRECTION_VECTORS,
    AnotoCodecAdapter,
    AnotoDecodeError,
)
from digital_pen.types import DecodedPose, DotDirection


@dataclass(frozen=True)
class WindowDecode:
    row: int
    col: int
    x: int
    y: int
    origin_x: int
    origin_y: int
    mean_direction_confidence: float
    completed_directions: np.ndarray


@dataclass(frozen=True)
class ConsensusResult:
    pose: DecodedPose
    supporting_windows: int
    decoded_windows: int
    candidate_windows: int
    mirrored: bool = False


def _validate_inputs(
    directions: np.ndarray,
    confidences: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(directions)
    weights = np.asarray(confidences, dtype=np.float64)
    if values.ndim != 2 or values.shape != weights.shape:
        raise ValueError(
            "directions and confidences must be equally shaped 2D matrices"
        )
    if values.shape[0] < 6 or values.shape[1] < 6:
        raise ValueError("direction matrix must contain at least one 6x6 window")
    finite_values = np.isfinite(values)
    if finite_values.any():
        integral = values[finite_values].astype(np.int64)
        if (
            not np.array_equal(values[finite_values], integral)
            or not np.isin(integral, range(4)).all()
        ):
            raise ValueError("finite direction values must be in range 0..3")
    finite_weights = np.isfinite(weights)
    if np.any((weights[finite_weights] < 0) | (weights[finite_weights] > 1)):
        raise ValueError("finite confidences must be between 0 and 1")
    return values.astype(np.float64, copy=False), weights


def decode_windows(
    directions: np.ndarray,
    confidences: np.ndarray,
    *,
    adapter: AnotoCodecAdapter | None = None,
    min_direction_confidence: float = 0.75,
    max_missing_directions: int = 1,
) -> tuple[list[WindowDecode], int]:
    """Decode each usable 6x6 window, completing a bounded number of gaps."""
    if not 0.0 <= min_direction_confidence <= 1.0:
        raise ValueError("min_direction_confidence must be between 0 and 1")
    if not 0 <= max_missing_directions <= 3:
        raise ValueError("max_missing_directions must be in range 0..3")
    values, weights = _validate_inputs(directions, confidences)
    codec = adapter or AnotoCodecAdapter()
    decoded: list[WindowDecode] = []
    candidate_windows = 0
    for row in range(values.shape[0] - 5):
        for col in range(values.shape[1] - 5):
            window = values[row : row + 6, col : col + 6]
            confidence_window = weights[row : row + 6, col : col + 6]
            known = (
                np.isfinite(window)
                & np.isfinite(confidence_window)
                & (confidence_window >= min_direction_confidence)
            )
            missing = np.argwhere(~known)
            if len(missing) > max_missing_directions:
                continue
            candidate_windows += 1
            observed_confidence = float(np.sum(confidence_window[known]) / 36.0)
            for replacements in product(range(4), repeat=len(missing)):
                completed = window.copy()
                for (missing_row, missing_col), replacement in zip(
                    missing, replacements, strict=True
                ):
                    completed[missing_row, missing_col] = replacement
                try:
                    x, y = codec.decode_position(completed)
                except AnotoDecodeError:
                    continue
                decoded.append(
                    WindowDecode(
                        row=row,
                        col=col,
                        x=x,
                        y=y,
                        origin_x=x - col,
                        origin_y=y - row,
                        mean_direction_confidence=observed_confidence,
                        completed_directions=completed,
                    )
                )
    return decoded, candidate_windows


def _adjacent_continuity(windows: list[WindowDecode]) -> float:
    by_location = {(item.row, item.col): item for item in windows}
    checked = 0
    continuous = 0
    for item in windows:
        for delta_row, delta_col in ((0, 1), (1, 0)):
            neighbor = by_location.get(
                (item.row + delta_row, item.col + delta_col)
            )
            if neighbor is None:
                continue
            checked += 1
            if (
                neighbor.x - item.x == delta_col
                and neighbor.y - item.y == delta_row
            ):
                continuous += 1
    return continuous / checked if checked else 1.0


def decode_consensus(
    directions: np.ndarray,
    confidences: np.ndarray,
    *,
    section: tuple[int, int],
    page_id: str,
    timestamp_us: int = 0,
    adapter: AnotoCodecAdapter | None = None,
    min_direction_confidence: float = 0.75,
    min_supporting_windows: int = 2,
    max_missing_directions: int = 1,
    position_bounds: tuple[int, int] | None = None,
    rotation_quadrants: int = 0,
    mirrored: bool = False,
) -> ConsensusResult:
    """Return the strongest common view-origin hypothesis from all windows."""
    if min_supporting_windows < 1:
        raise ValueError("min_supporting_windows must be positive")
    decoded, candidate_windows = decode_windows(
        directions,
        confidences,
        adapter=adapter,
        min_direction_confidence=min_direction_confidence,
        max_missing_directions=max_missing_directions,
    )
    if position_bounds is not None:
        max_x, max_y = position_bounds
        if max_x < 6 or max_y < 6:
            raise ValueError("position bounds must each be at least six")
        decoded = [
            item
            for item in decoded
            if 0 <= item.x <= max_x - 6 and 0 <= item.y <= max_y - 6
        ]
    if not decoded:
        if position_bounds is None:
            raise AnotoDecodeError("no eligible 6x6 window could be decoded")
        raise AnotoDecodeError("no decoded window lies within the pattern bounds")

    hypotheses: dict[
        tuple[int, int], dict[tuple[int, int], WindowDecode]
    ] = defaultdict(dict)
    for item in decoded:
        origin = (item.origin_x, item.origin_y)
        location = (item.row, item.col)
        previous = hypotheses[origin].get(location)
        if (
            previous is None
            or item.mean_direction_confidence > previous.mean_direction_confidence
        ):
            hypotheses[origin][location] = item
    ranked = sorted(
        (
            (origin, list(by_location.values()))
            for origin, by_location in hypotheses.items()
        ),
        key=lambda item: (
            sum(window.mean_direction_confidence for window in item[1]),
            len(item[1]),
        ),
        reverse=True,
    )
    codec = adapter or AnotoCodecAdapter()
    selected: tuple[tuple[int, int], list[WindowDecode]] | None = None
    for origin, group in ranked:
        if len(group) < min_supporting_windows:
            break
        representative = max(
            group, key=lambda item: item.mean_direction_confidence
        )
        try:
            codec.validate_section(
                representative.completed_directions,
                (representative.x, representative.y),
                section,
            )
        except AnotoDecodeError:
            continue
        selected = origin, group
        break
    if selected is None:
        best_support = len(ranked[0][1])
        if best_support < min_supporting_windows:
            raise AnotoDecodeError(
                f"best coordinate hypothesis has only {best_support} supporting windows"
            )
        raise AnotoDecodeError("no supported coordinate matches the expected section")
    (origin_x, origin_y), support = selected

    decoded_locations = {(item.row, item.col) for item in decoded}
    support_locations = {(item.row, item.col) for item in support}
    support_ratio = len(support_locations) / len(decoded_locations)
    mean_confidence = float(
        np.mean([item.mean_direction_confidence for item in support])
    )
    continuity = _adjacent_continuity(support)
    evidence = 1.0 - exp(-len(support_locations) / 3.0)
    confidence = float(
        np.clip(support_ratio * mean_confidence * continuity * evidence, 0.0, 1.0)
    )
    pose = DecodedPose(
        timestamp_us=timestamp_us,
        page_id=page_id,
        x_grid=float(origin_x),
        y_grid=float(origin_y),
        rotation_quadrants=rotation_quadrants,
        confidence=confidence,
    )
    return ConsensusResult(
        pose=pose,
        supporting_windows=len(support_locations),
        decoded_windows=len(decoded_locations),
        candidate_windows=candidate_windows,
        mirrored=mirrored,
    )


_VECTOR_DIRECTIONS = {value: key for key, value in DIRECTION_VECTORS.items()}


def transform_direction_matrix(
    directions: np.ndarray,
    confidences: np.ndarray,
    *,
    rotate_ccw: int = 0,
    mirror_horizontal: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply a spatial transform and the matching direction-label transform."""
    values, weights = _validate_inputs(directions, confidences)
    transformed = values.copy()
    transformed_weights = weights.copy()
    if mirror_horizontal:
        transformed = np.fliplr(transformed)
        transformed_weights = np.fliplr(transformed_weights)
    turns = rotate_ccw % 4
    if turns:
        transformed = np.rot90(transformed, k=turns)
        transformed_weights = np.rot90(transformed_weights, k=turns)

    finite = np.isfinite(transformed)
    for row, col in np.argwhere(finite):
        direction = DotDirection(int(transformed[row, col]))
        dx, dy = DIRECTION_VECTORS[direction]
        if mirror_horizontal:
            dx = -dx
        for _ in range(turns):
            dx, dy = -dy, dx
        transformed[row, col] = int(_VECTOR_DIRECTIONS[(dx, dy)])
    return transformed, transformed_weights


def decode_oriented_consensus(
    directions: np.ndarray,
    confidences: np.ndarray,
    *,
    section: tuple[int, int],
    page_id: str,
    timestamp_us: int = 0,
    adapter: AnotoCodecAdapter | None = None,
    min_direction_confidence: float = 0.75,
    min_supporting_windows: int = 2,
    max_missing_directions: int = 1,
    position_bounds: tuple[int, int] | None = None,
    allow_mirror: bool = True,
) -> ConsensusResult:
    """Try the four rotations and, optionally, the mirrored camera image."""
    codec = adapter or AnotoCodecAdapter()
    results: list[ConsensusResult] = []
    for mirrored in ((False, True) if allow_mirror else (False,)):
        for normalize_turns in range(4):
            transformed, transformed_confidences = transform_direction_matrix(
                directions,
                confidences,
                rotate_ccw=normalize_turns,
                mirror_horizontal=mirrored,
            )
            try:
                result = decode_consensus(
                    transformed,
                    transformed_confidences,
                    section=section,
                    page_id=page_id,
                    timestamp_us=timestamp_us,
                    adapter=codec,
                    min_direction_confidence=min_direction_confidence,
                    min_supporting_windows=min_supporting_windows,
                    max_missing_directions=max_missing_directions,
                    position_bounds=position_bounds,
                    rotation_quadrants=(
                        normalize_turns if mirrored else (-normalize_turns) % 4
                    ),
                    mirrored=mirrored,
                )
            except AnotoDecodeError:
                continue
            results.append(result)
    if not results:
        raise AnotoDecodeError("no orientation produced a supported coordinate")
    return max(
        results,
        key=lambda item: (
            item.supporting_windows,
            item.pose.confidence,
            item.decoded_windows,
        ),
    )
