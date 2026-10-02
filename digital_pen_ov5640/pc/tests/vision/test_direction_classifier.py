from __future__ import annotations

import numpy as np
import pytest

from digital_pen.types import (
    DirectionObservation,
    DotDirection,
    DotObservation,
    LatticeModel,
)


@pytest.mark.parametrize(
    ("dx", "dy", "expected_direction", "expected_confidence"),
    [
        (0.18, 0.02, DotDirection.RIGHT, 0.9),
        (-0.16, 0.04, DotDirection.LEFT, 0.8),
        (0.03, -0.17, DotDirection.UP, 0.85),
        (-0.05, 0.15, DotDirection.DOWN, 0.75),
    ],
)
def test_classify_direction_uses_the_dominant_residual_axis(
    dx: float,
    dy: float,
    expected_direction: DotDirection,
    expected_confidence: float,
) -> None:
    from digital_pen.vision.direction_classifier import classify_direction

    direction, confidence = classify_direction(dx, dy)

    assert direction is expected_direction
    assert confidence == pytest.approx(expected_confidence)


def test_classify_direction_rejects_an_offset_below_the_threshold() -> None:
    from digital_pen.vision.direction_classifier import classify_direction

    with pytest.raises(ValueError, match="below confidence threshold"):
        classify_direction(0.04, -0.07)


def test_classify_observations_maps_image_centers_back_to_grid() -> None:
    from digital_pen.vision.direction_classifier import classify_observations

    grid_to_image = np.array(
        [
            [18.0, 1.5, 40.0],
            [0.75, 20.0, 30.0],
            [0.002, -0.001, 1.0],
        ]
    )

    def project(col: float, row: float) -> tuple[float, float]:
        point = grid_to_image @ np.array([col, row, 1.0])
        return float(point[0] / point[2]), float(point[1] / point[2])

    observations = [
        DotObservation(project(2.18, 1.02), 12.0, 0.9),
        DotObservation(project(3.01, 4.17), 11.0, 0.8),
        DotObservation(project(5.04, 2.03), 10.0, 0.95),
    ]
    lattice = LatticeModel(grid_to_image, spacing_px=19.0, rms_error_px=0.2)

    result = classify_observations(observations, lattice)

    assert [(item.row, item.col, item.direction) for item in result] == [
        (1, 2, DotDirection.RIGHT),
        (4, 3, DotDirection.DOWN),
    ]
    assert result[0].residual_grid == pytest.approx((0.18, 0.02))
    assert result[1].residual_grid == pytest.approx((0.01, 0.17))


def test_build_direction_matrix_keeps_only_confident_best_observations() -> None:
    from digital_pen.anoto.matrix_builder import build_direction_matrix

    observations = [
        DirectionObservation(0, 1, DotDirection.UP, (0.01, -0.15), 0.93),
        DirectionObservation(1, 0, DotDirection.LEFT, (-0.14, 0.03), 0.72),
        DirectionObservation(1, 2, DotDirection.RIGHT, (0.15, 0.02), 0.81),
        DirectionObservation(1, 2, DotDirection.DOWN, (0.02, 0.19), 0.96),
    ]

    matrix = build_direction_matrix(
        observations,
        min_confidence=0.8,
        shape=(2, 3),
    )

    assert matrix.dtype == np.float64
    assert matrix.shape == (2, 3)
    assert np.isnan(matrix[0, 0])
    assert matrix[0, 1] == DotDirection.UP
    assert np.isnan(matrix[1, 0])
    assert matrix[1, 2] == DotDirection.DOWN


def test_classify_grid_fit_excludes_ransac_outliers() -> None:
    from digital_pen.vision.direction_classifier import classify_grid_fit
    from digital_pen.vision.grid_fitter import GridFitResult

    lattice = LatticeModel(np.eye(3), spacing_px=1.0, rms_error_px=0.1)
    observations = [
        DotObservation((1.2, 1.0), 10.0, 0.9),
        DotObservation((8.4, 7.0), 30.0, 0.2),
    ]
    fit = GridFitResult(
        model=lattice,
        assignments=[],
        inlier_mask=np.array([True, False]),
        inlier_ratio=0.5,
        offset_ratio=0.2,
    )

    result = classify_grid_fit(observations, fit)

    assert [(item.row, item.col, item.direction) for item in result] == [
        (1, 1, DotDirection.RIGHT)
    ]


def test_homography_validation_is_scale_invariant() -> None:
    from digital_pen.vision.perspective import validate_homography

    np.testing.assert_allclose(validate_homography(np.eye(3) * 1e-6), np.eye(3))
