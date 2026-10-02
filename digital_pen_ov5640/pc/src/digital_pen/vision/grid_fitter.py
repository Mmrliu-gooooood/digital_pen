"""Robust lattice indexing and homography fitting for Anoto dot centers."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from digital_pen.types import DotObservation, LatticeModel
from digital_pen.vision.perspective import (
    estimate_homography,
    inverse_project_points,
    median_grid_spacing,
    project_points,
    refine_homography,
)


@dataclass(frozen=True)
class GridFitterConfig:
    neighbor_count: int = 8
    angle_bins: int = 180
    max_offset_ratio: float = 0.42
    axis_tolerance_ratio: float = 0.16
    phase_tolerance_ratio: float = 0.09
    max_iterations: int = 8

    def __post_init__(self) -> None:
        if self.neighbor_count < 4:
            raise ValueError("neighbor_count must be at least four")
        if self.angle_bins < 36:
            raise ValueError("angle_bins must be at least 36")
        if not 0 < self.max_offset_ratio < 0.5:
            raise ValueError("max_offset_ratio must be between zero and 0.5")
        if not 0 < self.axis_tolerance_ratio < 0.5:
            raise ValueError("axis_tolerance_ratio must be between zero and 0.5")
        if not 0 < self.phase_tolerance_ratio < 0.25:
            raise ValueError("phase_tolerance_ratio must be between zero and 0.25")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be positive")


@dataclass(frozen=True)
class GridAssignment:
    observation_index: int
    row: int
    col: int
    residual_grid: tuple[float, float]
    reprojection_error_px: float


@dataclass(frozen=True)
class GridFitResult:
    model: LatticeModel
    assignments: list[GridAssignment]
    inlier_mask: np.ndarray
    inlier_ratio: float
    offset_ratio: float


def _circular_distance(values: np.ndarray, phase: float) -> np.ndarray:
    return np.abs((values - phase + 0.5) % 1.0 - 0.5)


def _estimate_phase(values: np.ndarray, tolerance: float) -> float:
    residues = np.mod(values, 1.0)
    # Unshifted dots make the largest of the three Anoto residual clusters.
    scores = np.array(
        [
            np.sum(
                np.maximum(
                    0.0,
                    1.0 - _circular_distance(residues, item) / tolerance,
                )
            )
            for item in residues
        ]
    )
    phase = float(residues[int(np.argmax(scores))])
    close = _circular_distance(residues, phase) < tolerance
    signed = (residues[close] - phase + 0.5) % 1.0 - 0.5
    return float((phase + np.median(signed)) % 1.0)


def _neighbor_vectors(points: np.ndarray, count: int) -> np.ndarray:
    neighbor_count = min(count, len(points) - 1)
    if len(points) <= 512:
        delta = points[None, :, :] - points[:, None, :]
        distance_sq = np.sum(delta * delta, axis=2)
        np.fill_diagonal(distance_sq, np.inf)
        neighbors = np.argpartition(distance_sq, neighbor_count, axis=1)[
            :, :neighbor_count
        ]
    else:
        # Keep full-page (typically 3025-dot) fitting bounded in memory.
        source = points.astype(np.float32)
        index = cv2.flann_Index(source, {"algorithm": 1, "trees": 4})
        candidates, _ = index.knnSearch(
            source, neighbor_count + 1, params={"checks": 64}
        )
        neighbors = np.empty((len(points), neighbor_count), dtype=np.int32)
        for row, candidate_indices in enumerate(candidates):
            without_self = candidate_indices[candidate_indices != row]
            if len(without_self) < neighbor_count:
                raise ValueError("could not find enough distinct neighboring points")
            neighbors[row] = without_self[:neighbor_count]
    vectors = points[neighbors] - points[:, None, :]
    return vectors.reshape(-1, 2)


def _estimate_basis(points: np.ndarray, config: GridFitterConfig) -> np.ndarray:
    vectors = _neighbor_vectors(points, config.neighbor_count)
    lengths = np.linalg.norm(vectors, axis=1)
    usable = np.isfinite(lengths) & (lengths > 1e-6)
    vectors = vectors[usable]
    lengths = lengths[usable]
    if len(vectors) < 8:
        raise ValueError("not enough distinct neighboring points to estimate a grid")

    angles = np.mod(np.arctan2(vectors[:, 1], vectors[:, 0]), np.pi)
    bins = config.angle_bins
    indices = np.floor(angles * bins / np.pi).astype(int) % bins
    typical = float(np.percentile(lengths, 15))
    weights = 1.0 / np.maximum(lengths, typical * 0.35)
    histogram = np.bincount(indices, weights=weights, minlength=bins)
    # Smooth circularly, then score orthogonal angle pairs together.
    histogram = sum(np.roll(histogram, shift) for shift in range(-3, 4))
    quarter_turn = bins // 2
    pair_score = histogram + np.roll(histogram, -quarter_turn)
    peak = int(np.argmax(pair_score))
    angle = (peak + 0.5) * np.pi / bins

    units = np.array(
        [
            [np.cos(angle), np.sin(angle)],
            [-np.sin(angle), np.cos(angle)],
        ]
    )
    basis_vectors: list[np.ndarray] = []
    angular_tolerance = np.deg2rad(13.0)
    for unit in units:
        projections = vectors @ unit
        perpendicular = np.abs(vectors[:, 0] * unit[1] - vectors[:, 1] * unit[0])
        aligned = (np.abs(projections) > 1e-6) & (
            np.arctan2(perpendicular, np.abs(projections)) < angular_tolerance
        )
        candidates = vectors[aligned].copy()
        projected = projections[aligned]
        candidates[projected < 0] *= -1.0
        projected = np.abs(projected)
        if len(candidates) < 4:
            raise ValueError("could not find two supported lattice directions")
        # Direction offsets split adjacent lengths into several clusters. The
        # true basis is the densest *vector* cluster (equal offsets cancel),
        # while a 1-D length mode can confuse it with a shifted neighbor.
        bandwidth = max(0.6, float(np.percentile(projected, 20)) * 0.10)
        sample_count = min(len(candidates), 2048)
        sample_indices = np.linspace(
            0, len(candidates) - 1, sample_count, dtype=np.int32
        )
        sample = candidates[sample_indices]
        cluster_distance = np.linalg.norm(
            sample[:, None, :] - sample[None, :, :], axis=2
        )
        density = np.count_nonzero(cluster_distance < bandwidth, axis=1)
        mode = sample[int(np.argmax(density))]
        local = np.linalg.norm(candidates - mode, axis=1) < bandwidth * 1.5
        basis_vectors.append(np.median(candidates[local], axis=0))

    first, second = basis_vectors
    if abs(first[0]) >= abs(second[0]):
        horizontal, vertical = first, second
    else:
        horizontal, vertical = second, first
    if horizontal[0] < 0:
        horizontal = -horizontal
    if vertical[1] < 0:
        vertical = -vertical
    basis = np.column_stack((horizontal, vertical))
    if abs(float(np.linalg.det(basis))) < 1e-6:
        raise ValueError("estimated lattice basis is degenerate")
    return basis


def _axis_offsets(residuals: np.ndarray, offset_ratio: float) -> np.ndarray:
    offsets = np.zeros_like(residuals)
    if offset_ratio <= 0:
        return offsets
    dominant = np.argmax(np.abs(residuals), axis=1)
    rows = np.arange(len(residuals))
    offsets[rows, dominant] = np.sign(residuals[rows, dominant]) * offset_ratio
    return offsets


def _estimate_offset_ratio(residuals: np.ndarray, axis_tolerance: float) -> float:
    absolute = np.abs(residuals)
    minor = np.min(absolute, axis=1)
    major = np.max(absolute, axis=1)
    cross_like = (minor < axis_tolerance) & (major < 0.45)
    values = major[cross_like]
    if len(values) == 0 or float(np.median(values)) < 0.055:
        return 0.0
    return float(np.median(values))


def fit_grid(
    observations: list[DotObservation],
    config: GridFitterConfig | None = None,
) -> GridFitResult:
    """Fit a perspective lattice, retaining robust index assignments."""
    settings = config or GridFitterConfig()
    if len(observations) < 16:
        raise ValueError("at least 16 dot observations are required")
    points = np.asarray([item.center_px for item in observations], dtype=np.float64)
    if not np.all(np.isfinite(points)) or len(np.unique(points, axis=0)) < 8:
        raise ValueError("dot centers must contain finite, distinct points")

    basis = _estimate_basis(points, settings)
    anchor = np.median(points, axis=0)
    approximate = (points - anchor) @ np.linalg.inv(basis).T
    phase = np.array(
        [
            _estimate_phase(approximate[:, axis], settings.phase_tolerance_ratio)
            for axis in range(2)
        ]
    )
    indices = np.rint(approximate - phase).astype(np.int32)
    initial_spacing = float(np.mean(np.linalg.norm(basis, axis=0)))
    homography, inliers = estimate_homography(
        indices,
        points,
        ransac_threshold_px=initial_spacing * 0.46,
    )

    offset_ratio = 0.0
    for _ in range(settings.max_iterations):
        normalized = inverse_project_points(points, homography)
        new_indices = np.rint(normalized).astype(np.int32)
        residuals = normalized - new_indices
        candidate_offset = min(
            settings.max_offset_ratio,
            _estimate_offset_ratio(residuals[inliers], settings.axis_tolerance_ratio),
        )
        corrected = new_indices + _axis_offsets(residuals, candidate_offset)
        spacing = median_grid_spacing(homography, new_indices[inliers])
        new_homography, ransac_mask = estimate_homography(
            corrected,
            points,
            ransac_threshold_px=max(0.65, spacing * 0.085),
        )
        projected = project_points(corrected, new_homography)
        errors = np.linalg.norm(projected - points, axis=1)
        pattern_mask = (
            (np.min(np.abs(residuals), axis=1) < settings.axis_tolerance_ratio)
            & (np.max(np.abs(residuals), axis=1) <= settings.max_offset_ratio + 0.03)
        )
        new_inliers = ransac_mask & pattern_mask
        if np.count_nonzero(new_inliers) < 8:
            raise ValueError("too few lattice inliers after robust fitting")
        converged = np.array_equal(new_indices, indices) and np.array_equal(
            new_inliers, inliers
        )
        indices = new_indices
        inliers = new_inliers
        homography = new_homography
        offset_ratio = candidate_offset
        if converged:
            break

    normalized = inverse_project_points(points, homography)
    indices = np.rint(normalized).astype(np.int32)
    residuals = normalized - indices
    corrected = indices + _axis_offsets(residuals, offset_ratio)
    projected = project_points(corrected, homography)
    errors = np.linalg.norm(projected - points, axis=1)
    spacing = median_grid_spacing(homography, indices[inliers])
    final_mask = inliers & (errors < max(0.75, spacing * 0.09))
    if np.count_nonzero(final_mask) < 8:
        raise ValueError("too few final lattice inliers")

    # RANSAC selects the robust support; refit all selected correspondences so
    # the public model and RMS describe the final least-squares optimum.
    homography = refine_homography(
        corrected[final_mask],
        points[final_mask],
    )
    normalized = inverse_project_points(points, homography)
    indices = np.rint(normalized).astype(np.int32)
    residuals = normalized - indices
    offset_ratio = min(
        settings.max_offset_ratio,
        _estimate_offset_ratio(residuals[final_mask], settings.axis_tolerance_ratio),
    )
    corrected = indices + _axis_offsets(residuals, offset_ratio)
    homography = refine_homography(corrected[final_mask], points[final_mask])
    projected = project_points(corrected, homography)
    errors = np.linalg.norm(projected - points, axis=1)

    minimum = np.min(indices[final_mask], axis=0)
    normalized_indices = indices - minimum
    translation = np.array(
        [[1.0, 0.0, minimum[0]], [0.0, 1.0, minimum[1]], [0.0, 0.0, 1.0]]
    )
    homography = homography @ translation
    spacing = median_grid_spacing(homography, normalized_indices[final_mask])
    rms = float(np.sqrt(np.mean(np.square(errors[final_mask]))))
    model = LatticeModel(
        grid_to_image=homography.astype(np.float64),
        spacing_px=spacing,
        rms_error_px=rms,
    )
    assignments = [
        GridAssignment(
            observation_index=index,
            row=int(normalized_indices[index, 1]),
            col=int(normalized_indices[index, 0]),
            residual_grid=(float(residuals[index, 0]), float(residuals[index, 1])),
            reprojection_error_px=float(errors[index]),
        )
        for index in np.flatnonzero(final_mask)
    ]
    return GridFitResult(
        model=model,
        assignments=assignments,
        inlier_mask=final_mask,
        inlier_ratio=float(np.count_nonzero(final_mask) / len(points)),
        offset_ratio=offset_ratio,
    )


def fit_lattice(
    observations: list[DotObservation],
    config: GridFitterConfig | None = None,
) -> LatticeModel:
    """Fit and return only the public lattice model."""
    return fit_grid(observations, config).model
