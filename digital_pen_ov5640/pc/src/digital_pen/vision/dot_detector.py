from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import pi

import cv2
import numpy as np

from digital_pen.types import DotObservation
from digital_pen.vision.preprocessing import PreprocessingConfig, preprocess_image


@dataclass(frozen=True)
class DotDetectorConfig(PreprocessingConfig):
    min_area_px: float = 3.0
    max_area_px: float = 200.0
    min_aspect_ratio: float = 0.5
    min_circularity: float = 0.5

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.min_area_px <= 0 or self.max_area_px < self.min_area_px:
            raise ValueError("area bounds must be positive and ordered")
        if not 0 < self.min_aspect_ratio <= 1:
            raise ValueError("min_aspect_ratio must be between 0 and 1")
        if not 0 <= self.min_circularity <= 1:
            raise ValueError("min_circularity must be between 0 and 1")


class RejectionReason(StrEnum):
    AREA_TOO_SMALL = "area_too_small"
    AREA_TOO_LARGE = "area_too_large"
    ASPECT_RATIO = "aspect_ratio"
    CIRCULARITY = "circularity"


@dataclass(frozen=True)
class DotCandidate:
    center_px: tuple[float, float]
    area_px: float
    circularity: float
    aspect_ratio: float
    bounding_box: tuple[int, int, int, int]
    accepted: bool
    rejection_reason: RejectionReason | None


@dataclass(frozen=True)
class DotDetectionResult:
    observations: list[DotObservation]
    binary: np.ndarray
    stages: dict[str, np.ndarray]
    candidates: list[DotCandidate]


def _weighted_center(gray: np.ndarray, contour: np.ndarray) -> tuple[float, float]:
    x, y, width, height = cv2.boundingRect(contour)
    mask = np.zeros((height, width), dtype=np.uint8)
    shifted = contour - np.array([[[x, y]]], dtype=contour.dtype)
    cv2.drawContours(mask, [shifted], -1, 255, thickness=-1)
    weights = (255.0 - gray[y : y + height, x : x + width].astype(np.float64)) * (
        mask.astype(np.float64) / 255.0
    )
    total = float(weights.sum())
    if total <= 0:
        moments = cv2.moments(contour)
        return (
            float(moments["m10"] / moments["m00"]),
            float(moments["m01"] / moments["m00"]),
        )
    yy, xx = np.indices(weights.shape, dtype=np.float64)
    return (
        float(x + np.sum(xx * weights) / total),
        float(y + np.sum(yy * weights) / total),
    )


def _analyze_dots(
    gray: np.ndarray,
    config: DotDetectorConfig,
    *,
    capture_stages: bool,
) -> DotDetectionResult:
    if not isinstance(gray, np.ndarray) or gray.ndim != 2 or gray.dtype != np.uint8:
        raise ValueError("gray must be a 2D uint8 NumPy array")
    preprocessed = preprocess_image(
        gray,
        config,
        capture_stages=capture_stages,
    )
    contours, _ = cv2.findContours(
        preprocessed.binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    observations: list[DotObservation] = []
    candidates: list[DotCandidate] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        x, y, width, height = cv2.boundingRect(contour)
        aspect_ratio = min(width, height) / max(width, height)
        perimeter = float(cv2.arcLength(contour, True))
        circularity = (
            min(1.0, 4.0 * pi * area / (perimeter * perimeter))
            if perimeter > 0
            else 0.0
        )
        moments = cv2.moments(contour)
        if moments["m00"] > 0:
            geometric_center = (
                float(moments["m10"] / moments["m00"]),
                float(moments["m01"] / moments["m00"]),
            )
        else:
            geometric_center = (x + (width - 1) / 2.0, y + (height - 1) / 2.0)

        reason: RejectionReason | None = None
        if area < config.min_area_px:
            reason = RejectionReason.AREA_TOO_SMALL
        elif area > config.max_area_px:
            reason = RejectionReason.AREA_TOO_LARGE
        elif aspect_ratio < config.min_aspect_ratio:
            reason = RejectionReason.ASPECT_RATIO
        elif circularity < config.min_circularity:
            reason = RejectionReason.CIRCULARITY

        center = geometric_center
        if reason is None:
            # Contours are expressed in the preprocessed image coordinate
            # system, so centroid weights must come from that same image
            # (especially after distortion correction or CLAHE).
            center = _weighted_center(preprocessed.processed_gray, contour)
            observations.append(
                DotObservation(
                    center_px=center,
                    area_px=area,
                    circularity=circularity,
                )
            )
        candidates.append(
            DotCandidate(
                center_px=center,
                area_px=area,
                circularity=circularity,
                aspect_ratio=aspect_ratio,
                bounding_box=(x, y, width, height),
                accepted=reason is None,
                rejection_reason=reason,
            )
        )

    observations.sort(key=lambda item: (item.center_px[1], item.center_px[0]))
    candidates.sort(key=lambda item: (item.center_px[1], item.center_px[0]))
    return DotDetectionResult(
        observations=observations,
        binary=preprocessed.binary,
        stages=preprocessed.stages,
        candidates=candidates,
    )


def analyze_dots(gray: np.ndarray, config: DotDetectorConfig) -> DotDetectionResult:
    """Run detection while retaining candidates and intermediate stage images."""
    return _analyze_dots(gray, config, capture_stages=True)


def detect_dots(
    gray: np.ndarray, config: DotDetectorConfig
) -> tuple[list[DotObservation], np.ndarray]:
    """Detect black dots; binary foreground pixels always have value 255."""
    result = _analyze_dots(gray, config, capture_stages=False)
    return result.observations, result.binary
