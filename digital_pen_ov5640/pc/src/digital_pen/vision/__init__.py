"""Monochrome dot and lattice vision for the PC reference pipeline."""

from digital_pen.vision.direction_classifier import (
    classify_direction,
    classify_grid_fit,
    classify_observations,
)
from digital_pen.vision.dot_detector import (
    DotCandidate,
    DotDetectionResult,
    DotDetectorConfig,
    RejectionReason,
    analyze_dots,
    detect_dots,
)
from digital_pen.vision.grid_fitter import (
    GridAssignment,
    GridFitResult,
    GridFitterConfig,
    fit_grid,
    fit_lattice,
)
from digital_pen.vision.perspective import (
    estimate_homography,
    inverse_project_points,
    median_grid_spacing,
    project_points,
    refine_homography,
    validate_homography,
)

__all__ = [
    "DotCandidate",
    "DotDetectionResult",
    "DotDetectorConfig",
    "GridAssignment",
    "GridFitResult",
    "GridFitterConfig",
    "RejectionReason",
    "analyze_dots",
    "classify_direction",
    "classify_grid_fit",
    "classify_observations",
    "detect_dots",
    "estimate_homography",
    "fit_grid",
    "fit_lattice",
    "inverse_project_points",
    "median_grid_spacing",
    "project_points",
    "refine_homography",
    "validate_homography",
]
