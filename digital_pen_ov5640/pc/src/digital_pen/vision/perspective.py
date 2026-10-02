"""Numerically checked homography helpers for the lattice pipeline."""

from __future__ import annotations

import cv2
import numpy as np


def validate_homography(homography: np.ndarray) -> np.ndarray:
    """Return a normalized float64 homography or raise ``ValueError``."""
    matrix = np.asarray(homography, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("homography must be a finite 3x3 matrix")
    magnitude = float(np.max(np.abs(matrix)))
    if magnitude == 0:
        raise ValueError("homography must be non-zero")
    matrix = matrix / magnitude
    if (
        abs(float(np.linalg.det(matrix))) < 1e-12
        or float(np.linalg.cond(matrix)) > 1e12
    ):
        raise ValueError("homography must be invertible")
    scale = float(matrix[2, 2])
    if abs(scale) < 1e-12:
        return matrix
    return matrix / scale


def project_points(points: np.ndarray, homography: np.ndarray) -> np.ndarray:
    """Project an ``(N, 2)`` array through a homography."""
    coordinates = np.asarray(points, dtype=np.float64)
    if coordinates.ndim != 2 or coordinates.shape[1] != 2:
        raise ValueError("points must have shape (N, 2)")
    matrix = validate_homography(homography)
    homogeneous = np.column_stack((coordinates, np.ones(len(coordinates))))
    projected = homogeneous @ matrix.T
    denominator = projected[:, 2]
    if np.any(np.abs(denominator) < 1e-12):
        raise ValueError("homography maps a point to infinity")
    result = projected[:, :2] / denominator[:, None]
    if not np.all(np.isfinite(result)):
        raise ValueError("homography produced non-finite coordinates")
    return result


def inverse_project_points(points: np.ndarray, homography: np.ndarray) -> np.ndarray:
    """Map image points back into normalized grid coordinates."""
    matrix = validate_homography(homography)
    return project_points(points, np.linalg.inv(matrix))


def estimate_homography(
    grid_points: np.ndarray,
    image_points: np.ndarray,
    *,
    ransac_threshold_px: float,
    max_iterations: int = 4000,
    confidence: float = 0.999,
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate a grid-to-image homography and its RANSAC inlier mask."""
    source = np.asarray(grid_points, dtype=np.float64)
    target = np.asarray(image_points, dtype=np.float64)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 2:
        raise ValueError("grid_points and image_points must share shape (N, 2)")
    if len(source) < 4:
        raise ValueError("at least four point correspondences are required")
    if ransac_threshold_px <= 0:
        raise ValueError("ransac_threshold_px must be positive")
    matrix, mask = cv2.findHomography(
        source,
        target,
        cv2.RANSAC,
        ransac_threshold_px,
        maxIters=max_iterations,
        confidence=confidence,
    )
    if matrix is None or mask is None:
        raise ValueError("could not estimate a non-degenerate homography")
    return validate_homography(matrix), mask.ravel().astype(bool)


def refine_homography(
    grid_points: np.ndarray,
    image_points: np.ndarray,
) -> np.ndarray:
    """Least-squares refine a homography after robust inlier selection."""
    source = np.asarray(grid_points, dtype=np.float64)
    target = np.asarray(image_points, dtype=np.float64)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 2:
        raise ValueError("grid_points and image_points must share shape (N, 2)")
    if len(source) < 4:
        raise ValueError("at least four point correspondences are required")
    matrix, _ = cv2.findHomography(source, target, 0)
    if matrix is None:
        raise ValueError("could not refine a non-degenerate homography")
    return validate_homography(matrix)


def median_grid_spacing(homography: np.ndarray, grid_points: np.ndarray) -> float:
    """Measure the median projected one-cell spacing over a fitted region."""
    points = np.asarray(grid_points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) == 0:
        raise ValueError("grid_points must be a non-empty (N, 2) array")
    centers = project_points(points, homography)
    along_x = project_points(points + (1.0, 0.0), homography)
    along_y = project_points(points + (0.0, 1.0), homography)
    distances = np.concatenate(
        (
            np.linalg.norm(along_x - centers, axis=1),
            np.linalg.norm(along_y - centers, axis=1),
        )
    )
    spacing = float(np.median(distances))
    if not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("homography has no positive finite grid spacing")
    return spacing
