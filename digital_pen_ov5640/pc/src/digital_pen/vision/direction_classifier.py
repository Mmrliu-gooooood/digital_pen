"""Classify monochrome Anoto dot offsets relative to lattice centers."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from digital_pen.types import (
    DirectionObservation,
    DotDirection,
    DotObservation,
    LatticeModel,
)

if TYPE_CHECKING:
    from digital_pen.vision.grid_fitter import GridFitResult


def classify_direction(
    dx: float,
    dy: float,
    min_offset: float = 0.08,
) -> tuple[DotDirection, float]:
    """Return the direction and dominant-axis confidence of one grid residual."""
    if not all(math.isfinite(value) for value in (dx, dy, min_offset)):
        raise ValueError("direction offsets and threshold must be finite")
    if min_offset < 0:
        raise ValueError("min_offset must be non-negative")

    axis = max(abs(dx), abs(dy))
    if axis < min_offset:
        raise ValueError("direction offset is below confidence threshold")
    confidence = axis / (abs(dx) + abs(dy) + 1e-9)
    if abs(dx) > abs(dy):
        direction = DotDirection.RIGHT if dx > 0 else DotDirection.LEFT
    else:
        direction = DotDirection.DOWN if dy > 0 else DotDirection.UP
    return direction, confidence


def classify_observations(
    observations: list[DotObservation],
    lattice: LatticeModel,
    min_offset: float = 0.08,
) -> list[DirectionObservation]:
    """Map image-space dot centers to indexed, classified grid observations.

    Dots whose normalized residual is below ``min_offset`` are ambiguous and
    are omitted. Points mapping outside the non-negative fitted lattice are
    treated as outliers and omitted as well.
    """
    try:
        image_to_grid = np.linalg.inv(lattice.grid_to_image)
    except np.linalg.LinAlgError as error:
        raise ValueError("grid_to_image must be invertible") from error

    classified: list[DirectionObservation] = []
    for observation in observations:
        x_px, y_px = observation.center_px
        grid_h = image_to_grid @ np.array([x_px, y_px, 1.0], dtype=np.float64)
        if not np.all(np.isfinite(grid_h)) or abs(grid_h[2]) < 1e-12:
            continue

        col_grid = float(grid_h[0] / grid_h[2])
        row_grid = float(grid_h[1] / grid_h[2])
        col = int(np.rint(col_grid))
        row = int(np.rint(row_grid))
        if row < 0 or col < 0:
            continue

        dx = col_grid - col
        dy = row_grid - row
        if max(abs(dx), abs(dy)) < min_offset:
            continue
        direction, confidence = classify_direction(dx, dy, min_offset)
        classified.append(
            DirectionObservation(
                row=row,
                col=col,
                direction=direction,
                residual_grid=(dx, dy),
                confidence=confidence,
            )
        )
    return classified


def classify_grid_fit(
    observations: list[DotObservation],
    fit: GridFitResult,
    min_offset: float = 0.08,
) -> list[DirectionObservation]:
    """Classify only the observations retained by robust lattice fitting."""
    if fit.inlier_mask.shape != (len(observations),):
        raise ValueError("fit inlier mask must match the observation count")
    inliers = [
        observation
        for observation, keep in zip(observations, fit.inlier_mask, strict=True)
        if keep
    ]
    return classify_observations(inliers, fit.model, min_offset)
