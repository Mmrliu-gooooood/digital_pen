from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest


def _synthetic_dots(
    centers: list[tuple[float, float]],
    *,
    shape: tuple[int, int] = (96, 128),
    radius: float = 3.25,
    scale: int = 8,
) -> np.ndarray:
    """Render deterministic anti-aliased black dots on a brightness gradient."""
    height, width = shape
    large = np.full((height * scale, width * scale), 255, dtype=np.uint8)
    for x, y in centers:
        # OpenCV's integer coordinates address pixel centers. Account for the
        # half-pixel shift introduced when the supersampled image is reduced.
        rendered_x = round((x + 0.5) * scale - 0.5)
        rendered_y = round((y + 0.5) * scale - 0.5)
        cv2.circle(
            large,
            (rendered_x, rendered_y),
            round(radius * scale),
            0,
            thickness=-1,
            lineType=cv2.LINE_AA,
        )

    image = cv2.resize(large, (width, height), interpolation=cv2.INTER_AREA)
    gradient = np.linspace(0, 28, width, dtype=np.float32)[None, :]
    image = np.clip(image.astype(np.float32) - gradient, 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(image, (3, 3), 0.55)


def test_detect_dots_finds_subpixel_centers_on_uneven_background() -> None:
    from digital_pen.vision import DotDetectorConfig, detect_dots

    expected = [(23.25, 20.75), (63.625, 42.375), (101.125, 73.5)]
    gray = _synthetic_dots(expected)
    config = DotDetectorConfig(
        min_area_px=18,
        max_area_px=70,
        min_aspect_ratio=0.65,
        min_circularity=0.65,
        threshold_method="adaptive",
        adaptive_block_size=31,
        adaptive_c=7.0,
        morphology_enabled=False,
        clahe_enabled=False,
    )

    observations, binary = detect_dots(gray, config)

    assert binary.dtype == np.uint8
    assert binary.shape == gray.shape
    assert set(np.unique(binary)).issubset({0, 255})
    assert len(observations) == len(expected)
    actual = sorted(observation.center_px for observation in observations)
    for measured, truth in zip(actual, sorted(expected), strict=True):
        assert np.hypot(measured[0] - truth[0], measured[1] - truth[1]) < 0.25


def test_detect_dots_supports_otsu_and_rejects_non_dot_components() -> None:
    from digital_pen.vision import DotDetectorConfig, detect_dots

    gray = _synthetic_dots([(29.5, 31.5)], radius=4.0)
    cv2.rectangle(gray, (55, 28), (80, 31), 0, thickness=-1)
    cv2.circle(gray, (103, 55), 9, 0, thickness=-1)
    config = DotDetectorConfig(
        min_area_px=25,
        max_area_px=85,
        min_aspect_ratio=0.7,
        min_circularity=0.7,
        threshold_method="otsu",
        morphology_enabled=False,
        clahe_enabled=False,
    )

    observations, binary = detect_dots(gray, config)

    assert len(observations) == 1
    assert np.hypot(
        observations[0].center_px[0] - 29.5,
        observations[0].center_px[1] - 31.5,
    ) < 0.25
    assert binary[32, 30] == 255
    assert binary[0, 0] == 0


@pytest.mark.parametrize(
    "gray",
    [
        np.zeros((12, 16, 3), dtype=np.uint8),
        np.zeros((12, 16), dtype=np.float32),
    ],
)
def test_detect_dots_rejects_non_grayscale_uint8_images(gray: np.ndarray) -> None:
    from digital_pen.vision import DotDetectorConfig, detect_dots

    with pytest.raises(ValueError, match="2D uint8"):
        detect_dots(gray, DotDetectorConfig())


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"min_area_px": 10, "max_area_px": 5}, "area"),
        ({"min_aspect_ratio": 0}, "aspect"),
        ({"min_circularity": 1.1}, "circularity"),
        ({"threshold_method": "fixed"}, "threshold_method"),
        ({"adaptive_block_size": 4}, "adaptive_block_size"),
        ({"morphology_kernel_size": 2}, "morphology_kernel_size"),
        ({"morphology_iterations": -1}, "morphology_iterations"),
        (
            {
                "undistort_enabled": True,
                "camera_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "distortion_coefficients": np.zeros(5),
            },
            "camera_matrix",
        ),
        (
            {
                "undistort_enabled": True,
                "camera_matrix": np.eye(3),
                "distortion_coefficients": np.zeros((2, 2)),
            },
            "distortion_coefficients",
        ),
    ],
)
def test_detector_config_rejects_invalid_values(
    kwargs: dict[str, object], message: str
) -> None:
    from digital_pen.vision import DotDetectorConfig

    with pytest.raises(ValueError, match=message):
        DotDetectorConfig(**kwargs)


def test_analysis_can_capture_each_enabled_preprocessing_stage() -> None:
    from digital_pen.vision import DotDetectorConfig, analyze_dots

    gray = _synthetic_dots([(40.0, 40.0)])
    config = DotDetectorConfig(
        min_area_px=10,
        max_area_px=100,
        undistort_enabled=True,
        camera_matrix=np.array(
            [[100.0, 0.0, 64.0], [0.0, 100.0, 48.0], [0.0, 0.0, 1.0]]
        ),
        distortion_coefficients=np.zeros(5),
        clahe_enabled=True,
        morphology_enabled=True,
        morphology_kernel_size=3,
    )

    result = analyze_dots(gray, config)

    assert list(result.stages) == [
        "input",
        "undistorted",
        "clahe",
        "threshold",
        "morphology",
    ]
    assert result.binary.dtype == np.uint8
    assert set(np.unique(result.binary)).issubset({0, 255})


def test_threshold_stage_can_be_disabled_for_binary_camera_input() -> None:
    from digital_pen.vision import DotDetectorConfig, analyze_dots

    gray = np.full((48, 64), 255, dtype=np.uint8)
    cv2.circle(gray, (24, 20), 4, 0, thickness=-1)
    config = DotDetectorConfig(
        min_area_px=20,
        max_area_px=80,
        threshold_enabled=False,
        morphology_enabled=False,
    )

    result = analyze_dots(gray, config)

    assert len(result.observations) == 1
    assert list(result.stages) == ["input", "binary_input"]
    assert result.binary[20, 24] == 255
    assert result.binary[0, 0] == 0


def test_inspect_dots_cli_writes_annotation_binary_and_stage_images(
    tmp_path: Path,
) -> None:
    from pc.apps.inspect_dots import main

    source = tmp_path / "frame.pgm"
    annotated = tmp_path / "annotated.png"
    binary = tmp_path / "binary.png"
    stages = tmp_path / "stages"
    gray = _synthetic_dots([(32.0, 28.0), (78.0, 57.0)])
    assert cv2.imwrite(str(source), gray)

    exit_code = main(
        [
            "--image",
            str(source),
            "--annotated",
            str(annotated),
            "--binary",
            str(binary),
            "--stages-dir",
            str(stages),
            "--threshold-method",
            "adaptive",
            "--adaptive-block-size",
            "31",
            "--adaptive-c",
            "7",
            "--min-area",
            "18",
            "--max-area",
            "70",
            "--min-circularity",
            "0.65",
            "--disable-morphology",
        ]
    )

    assert exit_code == 0
    assert cv2.imread(str(annotated), cv2.IMREAD_COLOR).shape == (*gray.shape, 3)
    np.testing.assert_array_equal(
        cv2.imread(str(binary), cv2.IMREAD_GRAYSCALE) > 0,
        cv2.imread(str(stages / "threshold.png"), cv2.IMREAD_GRAYSCALE) > 0,
    )
    assert (stages / "input.png").is_file()
