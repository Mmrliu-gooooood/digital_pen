from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np


def _validate_confidence(value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be between 0 and 1")


class DotDirection(IntEnum):
    UP = 0
    LEFT = 1
    RIGHT = 2
    DOWN = 3


@dataclass(frozen=True)
class CameraFrame:
    frame_id: int
    timestamp_us: int
    image: np.ndarray
    exposure: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.image, np.ndarray):
            raise ValueError("image must be a grayscale uint8 NumPy array")
        if self.image.ndim != 2 or self.image.dtype != np.uint8:
            raise ValueError("image must be a grayscale uint8 NumPy array")
        if self.frame_id < 0 or self.timestamp_us < 0:
            raise ValueError("frame_id and timestamp_us must be non-negative")


@dataclass(frozen=True)
class DotObservation:
    center_px: tuple[float, float]
    area_px: float
    circularity: float

    def __post_init__(self) -> None:
        if self.area_px <= 0:
            raise ValueError("area_px must be positive")
        if not 0.0 <= self.circularity <= 1.0:
            raise ValueError("circularity must be between 0 and 1")


@dataclass(frozen=True)
class LatticeModel:
    grid_to_image: np.ndarray
    spacing_px: float
    rms_error_px: float

    def __post_init__(self) -> None:
        if not isinstance(self.grid_to_image, np.ndarray):
            raise ValueError("grid_to_image must be a 3x3 NumPy array")
        if self.grid_to_image.shape != (3, 3):
            raise ValueError("grid_to_image must be a 3x3 NumPy array")
        if self.spacing_px <= 0 or self.rms_error_px < 0:
            raise ValueError("spacing must be positive and RMS error non-negative")


@dataclass(frozen=True)
class DirectionObservation:
    row: int
    col: int
    direction: DotDirection
    residual_grid: tuple[float, float]
    confidence: float

    def __post_init__(self) -> None:
        if self.row < 0 or self.col < 0:
            raise ValueError("row and col must be non-negative")
        _validate_confidence(self.confidence)


@dataclass(frozen=True)
class DecodedPose:
    timestamp_us: int
    page_id: str
    x_grid: float
    y_grid: float
    rotation_quadrants: int
    confidence: float

    def __post_init__(self) -> None:
        if self.timestamp_us < 0:
            raise ValueError("timestamp_us must be non-negative")
        if self.rotation_quadrants not in range(4):
            raise ValueError("rotation_quadrants must be in range 0..3")
        _validate_confidence(self.confidence)


@dataclass(frozen=True)
class PenPoint:
    timestamp_us: int
    x_mm: float
    y_mm: float
    confidence: float
    pen_down: bool

    def __post_init__(self) -> None:
        if self.timestamp_us < 0:
            raise ValueError("timestamp_us must be non-negative")
        _validate_confidence(self.confidence)
