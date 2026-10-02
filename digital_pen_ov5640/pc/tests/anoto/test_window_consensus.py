from __future__ import annotations

import microdots
import numpy as np
import pytest

from digital_pen.anoto import (
    AnotoDecodeError,
    decode_consensus,
    decode_oriented_consensus,
    decode_windows,
    transform_direction_matrix,
)


def _directions(section: tuple[int, int] = (10, 2)) -> np.ndarray:
    bits = microdots.anoto_6x6_a4_fixed.encode_bitmatrix((14, 17), section=section)
    return (bits[..., 0] + 2 * bits[..., 1]).astype(np.float64)


def test_consensus_recovers_view_origin_with_missing_and_bad_window() -> None:
    directions = _directions()
    confidences = np.full(directions.shape, 0.96)
    directions[:2, :2] = np.nan
    confidences[:2, :2] = np.nan
    # A corner corruption invalidates some windows but must not move consensus.
    directions[-1, -1] = (directions[-1, -1] + 1) % 4

    result = decode_consensus(
        directions,
        confidences,
        section=(10, 2),
        page_id="prototype-a",
        timestamp_us=123,
    )

    assert (result.pose.x_grid, result.pose.y_grid) == (0.0, 0.0)
    assert result.pose.timestamp_us == 123
    assert result.supporting_windows >= 40
    assert result.supporting_windows == result.decoded_windows - 1
    assert result.pose.confidence > 0.9


def test_consensus_recovers_windows_with_one_missing_direction() -> None:
    directions = _directions()
    confidences = np.full(directions.shape, 0.97)
    directions[6, 7] = np.nan
    confidences[6, 7] = np.nan

    result = decode_consensus(
        directions,
        confidences,
        section=(10, 2),
        page_id="prototype-a",
    )

    assert (result.pose.x_grid, result.pose.y_grid) == (0.0, 0.0)
    assert result.supporting_windows == result.decoded_windows


@pytest.mark.parametrize("missing_count", [2, 3])
def test_window_candidates_can_complete_a_few_missing_directions(
    missing_count: int,
) -> None:
    directions = _directions()[:6, :6]
    confidences = np.full(directions.shape, 0.97)
    for index in range(missing_count):
        directions[index, index] = np.nan
        confidences[index, index] = np.nan

    decoded, candidate_windows = decode_windows(
        directions,
        confidences,
        max_missing_directions=missing_count,
    )

    assert candidate_windows == 1
    assert any((item.x, item.y) == (0, 0) for item in decoded)


def test_position_bounds_prevent_expensive_section_validation() -> None:
    class HugePositionAdapter:
        def decode_position(self, directions: np.ndarray) -> tuple[int, int]:
            return (100_000_000, 100_000_000)

        def validate_section(self, *args) -> None:
            raise AssertionError("out-of-bounds position reached section validation")

    directions = np.zeros((6, 6), dtype=np.float64)
    confidences = np.ones((6, 6), dtype=np.float64)

    with pytest.raises(AnotoDecodeError, match="pattern bounds"):
        decode_consensus(
            directions,
            confidences,
            section=(10, 2),
            page_id="prototype-a",
            adapter=HugePositionAdapter(),  # type: ignore[arg-type]
            min_supporting_windows=1,
            position_bounds=(55, 55),
        )


@pytest.mark.parametrize("rotation", range(4))
@pytest.mark.parametrize("mirrored", [False, True])
def test_oriented_consensus_normalizes_rotation_and_mirror(
    rotation: int,
    mirrored: bool,
) -> None:
    canonical = _directions()
    confidence = np.full(canonical.shape, 0.98)
    observed, observed_confidence = transform_direction_matrix(
        canonical,
        confidence,
        rotate_ccw=rotation,
        mirror_horizontal=mirrored,
    )

    result = decode_oriented_consensus(
        observed,
        observed_confidence,
        section=(10, 2),
        page_id="prototype-a",
    )

    assert result.pose.rotation_quadrants == rotation
    assert result.mirrored is mirrored
    assert (result.pose.x_grid, result.pose.y_grid) == (0.0, 0.0)


def test_consensus_rejects_when_no_complete_window_exists() -> None:
    directions = _directions()
    confidences = np.full(directions.shape, 0.99)
    directions[:, ::2] = np.nan
    confidences[:, ::2] = np.nan

    with pytest.raises(AnotoDecodeError, match="no eligible"):
        decode_consensus(
            directions,
            confidences,
            section=(10, 2),
            page_id="prototype-a",
        )
