from __future__ import annotations

import numpy as np
import pytest


def _types_api():
    try:
        from digital_pen.types import (
            CameraFrame,
            DecodedPose,
            DirectionObservation,
            DotDirection,
            LatticeModel,
            PenPoint,
        )
    except ModuleNotFoundError:
        pytest.fail("digital_pen.types is not implemented")
    return (
        CameraFrame,
        DecodedPose,
        DirectionObservation,
        DotDirection,
        LatticeModel,
        PenPoint,
    )


def test_camera_frame_accepts_a_grayscale_uint8_image() -> None:
    CameraFrame, *_ = _types_api()
    image = np.zeros((240, 320), dtype=np.uint8)

    frame = CameraFrame(1, 1000, image, None)

    assert frame.image.shape == (240, 320)
    assert frame.image.dtype == np.uint8


@pytest.mark.parametrize(
    "image",
    [
        np.zeros((240, 320, 3), dtype=np.uint8),
        np.zeros((240, 320), dtype=np.float32),
    ],
)
def test_camera_frame_rejects_non_grayscale_or_non_uint8_images(
    image: np.ndarray,
) -> None:
    CameraFrame, *_ = _types_api()

    with pytest.raises(ValueError, match="grayscale uint8"):
        CameraFrame(1, 1000, image, None)


def test_lattice_model_requires_a_three_by_three_transform() -> None:
    _, _, _, _, LatticeModel, _ = _types_api()

    with pytest.raises(ValueError, match="3x3"):
        LatticeModel(np.eye(2), spacing_px=12.0, rms_error_px=0.2)


def test_confidence_fields_reject_values_outside_zero_to_one() -> None:
    _, DecodedPose, DirectionObservation, DotDirection, _, PenPoint = _types_api()

    with pytest.raises(ValueError, match="confidence"):
        DirectionObservation(0, 0, DotDirection.UP, (0.0, -0.16), 1.1)
    with pytest.raises(ValueError, match="confidence"):
        DecodedPose(1000, "page", 1.0, 2.0, 0, -0.1)
    with pytest.raises(ValueError, match="confidence"):
        PenPoint(1000, 1.0, 2.0, 1.2, False)
