from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class PreprocessingConfig:
    undistort_enabled: bool = False
    camera_matrix: np.ndarray | None = None
    distortion_coefficients: np.ndarray | None = None
    clahe_enabled: bool = False
    clahe_clip_limit: float = 2.0
    clahe_tile_grid_size: tuple[int, int] = (8, 8)
    threshold_enabled: bool = True
    threshold_method: str = "otsu"
    adaptive_block_size: int = 31
    adaptive_c: float = 5.0
    morphology_enabled: bool = True
    morphology_kernel_size: int = 3
    morphology_iterations: int = 1

    def __post_init__(self) -> None:
        if self.clahe_clip_limit <= 0:
            raise ValueError("clahe_clip_limit must be positive")
        if any(size <= 0 for size in self.clahe_tile_grid_size):
            raise ValueError("clahe_tile_grid_size values must be positive")
        if self.threshold_method not in {"otsu", "adaptive"}:
            raise ValueError("threshold_method must be 'otsu' or 'adaptive'")
        if self.adaptive_block_size < 3 or self.adaptive_block_size % 2 == 0:
            raise ValueError("adaptive_block_size must be an odd integer >= 3")
        if (
            self.morphology_kernel_size <= 0
            or self.morphology_kernel_size % 2 == 0
        ):
            raise ValueError("morphology_kernel_size must be a positive odd integer")
        if self.morphology_iterations < 0:
            raise ValueError("morphology_iterations must be non-negative")
        if self.undistort_enabled:
            if (
                not isinstance(self.camera_matrix, np.ndarray)
                or self.camera_matrix.shape != (3, 3)
                or not np.issubdtype(self.camera_matrix.dtype, np.number)
            ):
                raise ValueError(
                    "camera_matrix must be a numeric array with shape (3, 3) "
                    "when undistort is enabled"
                )
            coefficients = self.distortion_coefficients
            valid_coefficient_shape = (
                isinstance(coefficients, np.ndarray)
                and coefficients.size in {4, 5, 8, 12, 14}
                and (
                    coefficients.ndim == 1
                    or (coefficients.ndim == 2 and 1 in coefficients.shape)
                )
                and np.issubdtype(coefficients.dtype, np.number)
            )
            if not valid_coefficient_shape:
                raise ValueError(
                    "distortion_coefficients must be a numeric OpenCV coefficient "
                    "vector when undistort is enabled"
                )


@dataclass(frozen=True)
class PreprocessingResult:
    processed_gray: np.ndarray
    binary: np.ndarray
    stages: dict[str, np.ndarray]


def preprocess_image(
    gray: np.ndarray,
    config: PreprocessingConfig,
    *,
    capture_stages: bool = False,
) -> PreprocessingResult:
    """Preprocess a frame, returning a binary image with 255-valued dots."""
    current = gray
    stages = {"input": gray.copy()} if capture_stages else {}

    if config.undistort_enabled:
        if config.camera_matrix is None or config.distortion_coefficients is None:
            raise ValueError(
                "camera_matrix and distortion_coefficients are required "
                "when undistort is enabled"
            )
        current = cv2.undistort(
            current, config.camera_matrix, config.distortion_coefficients
        )
        if capture_stages:
            stages["undistorted"] = current.copy()

    if config.clahe_enabled:
        clahe = cv2.createCLAHE(
            clipLimit=config.clahe_clip_limit,
            tileGridSize=config.clahe_tile_grid_size,
        )
        current = clahe.apply(current)
        if capture_stages:
            stages["clahe"] = current.copy()

    if config.threshold_enabled:
        if config.threshold_method == "otsu":
            _, binary = cv2.threshold(
                current, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
            )
        elif config.threshold_method == "adaptive":
            binary = cv2.adaptiveThreshold(
                current,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                config.adaptive_block_size,
                config.adaptive_c,
            )
    else:
        values = np.unique(current)
        if not set(values.tolist()).issubset({0, 255}):
            raise ValueError("threshold can be disabled only for a binary input image")
        binary = cv2.bitwise_not(current)
    if capture_stages:
        stage_name = "threshold" if config.threshold_enabled else "binary_input"
        stages[stage_name] = binary.copy()

    if config.morphology_enabled:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (config.morphology_kernel_size, config.morphology_kernel_size),
        )
        binary = cv2.morphologyEx(
            binary,
            cv2.MORPH_OPEN,
            kernel,
            iterations=config.morphology_iterations,
        )
        binary = cv2.morphologyEx(
            binary,
            cv2.MORPH_CLOSE,
            kernel,
            iterations=config.morphology_iterations,
        )
        if capture_stages:
            stages["morphology"] = binary.copy()

    return PreprocessingResult(
        processed_gray=current,
        binary=binary,
        stages=stages,
    )
