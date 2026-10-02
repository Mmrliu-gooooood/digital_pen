"""Build decoder-ready direction matrices from classified dot observations."""

from __future__ import annotations

import numpy as np

from digital_pen.types import DirectionObservation


def build_direction_matrix(
    observations: list[DirectionObservation],
    *,
    min_confidence: float = 0.8,
    shape: tuple[int, int] | None = None,
) -> np.ndarray:
    """Return a float direction matrix with ``NaN`` for missing cells.

    Observations below ``min_confidence`` remain missing. If more than one
    observation maps to the same cell, the highest-confidence result wins.
    """
    directions, _ = build_direction_matrices(
        observations,
        min_confidence=min_confidence,
        shape=shape,
    )
    return directions


def build_direction_matrices(
    observations: list[DirectionObservation],
    *,
    min_confidence: float = 0.0,
    shape: tuple[int, int] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return aligned direction and confidence matrices with ``NaN`` gaps."""
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be between 0 and 1")
    if shape is None:
        if observations:
            shape = (
                max(item.row for item in observations) + 1,
                max(item.col for item in observations) + 1,
            )
        else:
            shape = (0, 0)
    rows, cols = shape
    if rows < 0 or cols < 0:
        raise ValueError("matrix shape must be non-negative")

    directions = np.full((rows, cols), np.nan, dtype=np.float64)
    confidences = np.full((rows, cols), np.nan, dtype=np.float64)
    for observation in observations:
        if observation.row >= rows or observation.col >= cols:
            raise ValueError("observation lies outside the requested matrix shape")
        if observation.confidence < min_confidence:
            continue
        current = confidences[observation.row, observation.col]
        if not np.isfinite(current) or observation.confidence > current:
            directions[observation.row, observation.col] = int(
                observation.direction
            )
            confidences[observation.row, observation.col] = observation.confidence
    return directions, confidences
