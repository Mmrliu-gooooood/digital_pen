from __future__ import annotations

import cv2
import numpy as np

from digital_pen.types import DotObservation


def _project(points: np.ndarray, homography: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(
        points.astype(np.float64)[None, :, :], homography
    )[0]


def test_fit_grid_recovers_indices_through_perspective_noise_and_outliers() -> None:
    from digital_pen.vision.grid_fitter import fit_grid

    rng = np.random.default_rng(20260906)
    rows, cols = 13, 16
    row_indices, col_indices = np.indices((rows, cols))
    nominal = np.column_stack((col_indices.ravel(), row_indices.ravel())).astype(
        np.float64
    )

    directions = rng.integers(0, 4, size=len(nominal))
    offset_ratio = 0.27
    offsets = np.zeros_like(nominal)
    offsets[directions == 0, 1] = -offset_ratio
    offsets[directions == 1, 0] = -offset_ratio
    offsets[directions == 2, 0] = offset_ratio
    offsets[directions == 3, 1] = offset_ratio

    angle = np.deg2rad(24.0)
    homography = np.array(
        [
            [17.2 * np.cos(angle), -16.5 * np.sin(angle), 94.0],
            [17.2 * np.sin(angle), 16.5 * np.cos(angle), 51.0],
            [8.0e-4, -6.0e-4, 1.0],
        ],
        dtype=np.float64,
    )
    image_points = _project(nominal + offsets, homography)
    image_points += rng.normal(0.0, 0.2, image_points.shape)

    keep = rng.random(len(nominal)) > 0.12
    keep[0] = True
    keep[cols - 1] = True
    keep[(rows - 1) * cols] = True
    kept_points = image_points[keep]
    kept_indices = np.column_stack((row_indices.ravel(), col_indices.ravel()))[keep]

    low = kept_points.min(axis=0) - 20.0
    high = kept_points.max(axis=0) + 20.0
    outliers = rng.uniform(low, high, size=(18, 2))
    all_points = np.vstack((kept_points, outliers))
    order = rng.permutation(len(all_points))
    observations = [
        DotObservation(tuple(point), area_px=12.0, circularity=0.85)
        for point in all_points[order]
    ]

    result = fit_grid(observations)

    original_positions = np.empty_like(order)
    original_positions[order] = np.arange(len(order))
    assignment_by_observation = {
        assignment.observation_index: (assignment.row, assignment.col)
        for assignment in result.assignments
    }
    recovered = np.array(
        [
            assignment_by_observation[original_positions[index]]
            for index in range(len(kept_points))
        ]
    )
    np.testing.assert_array_equal(recovered, kept_indices)
    assert result.inlier_mask.dtype == np.bool_
    assert result.inlier_mask.shape == (len(observations),)
    assert result.inlier_ratio > 0.85
    assert abs(result.offset_ratio - offset_ratio) < 0.04
    assert result.model.rms_error_px < 0.5

    from digital_pen.vision.direction_classifier import classify_grid_fit

    classified = classify_grid_fit(observations, result)
    recovered_directions = {
        (item.row, item.col): int(item.direction) for item in classified
    }
    expected_directions = directions[keep]
    for (row, col), expected_direction in zip(
        kept_indices, expected_directions, strict=True
    ):
        assert recovered_directions[(int(row), int(col))] == expected_direction


def test_fit_lattice_returns_public_model() -> None:
    from digital_pen.types import LatticeModel
    from digital_pen.vision.grid_fitter import fit_lattice

    observations = [
        DotObservation((20.0 + 12.0 * col, 30.0 + 12.0 * row), 10.0, 0.9)
        for row in range(5)
        for col in range(6)
    ]

    model = fit_lattice(observations)

    assert isinstance(model, LatticeModel)
    assert model.rms_error_px < 1e-6
