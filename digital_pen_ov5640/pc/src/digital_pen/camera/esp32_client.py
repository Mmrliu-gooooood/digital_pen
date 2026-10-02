from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import requests

from digital_pen.types import CameraFrame

_PGM_WHITESPACE = b" \t\r\n\v\f"


def _read_pgm_token(payload: bytes, offset: int) -> tuple[bytes, int]:
    while offset < len(payload):
        if payload[offset] in _PGM_WHITESPACE:
            offset += 1
            continue
        if payload[offset] == ord("#"):
            newline = payload.find(b"\n", offset)
            if newline < 0:
                raise ValueError("unterminated PGM comment")
            offset = newline + 1
            continue
        break

    start = offset
    while offset < len(payload) and payload[offset] not in _PGM_WHITESPACE:
        if payload[offset] == ord("#"):
            break
        offset += 1
    if start == offset:
        raise ValueError("PGM header is incomplete")
    return payload[start:offset], offset


def parse_pgm(payload: bytes) -> np.ndarray:
    """Parse an uncompressed, 8-bit binary PGM image."""
    offset = 0
    tokens: list[bytes] = []
    for _ in range(4):
        token, offset = _read_pgm_token(payload, offset)
        tokens.append(token)

    magic, width_raw, height_raw, max_value_raw = tokens
    if magic != b"P5":
        raise ValueError("PGM payload must use the binary P5 format")
    try:
        width = int(width_raw)
        height = int(height_raw)
        max_value = int(max_value_raw)
    except ValueError as exc:
        raise ValueError("PGM dimensions and max value must be integers") from exc
    if width <= 0 or height <= 0:
        raise ValueError("PGM dimensions must be positive")
    if max_value != 255:
        raise ValueError("PGM payload must contain 8-bit pixels with max value 255")
    if offset >= len(payload) or payload[offset] not in _PGM_WHITESPACE:
        raise ValueError("PGM header must be followed by whitespace")

    if payload[offset : offset + 2] == b"\r\n":
        offset += 2
    else:
        offset += 1
    pixels = payload[offset:]
    expected_bytes = width * height
    if len(pixels) != expected_bytes:
        raise ValueError(
            f"PGM pixel data has {len(pixels)} bytes; expected {expected_bytes}"
        )
    return np.frombuffer(pixels, dtype=np.uint8).reshape(height, width).copy()


def _required_header(headers: Mapping[str, str], name: str) -> int:
    value = headers.get(name)
    if value is None:
        raise ValueError(f"response is missing required {name} header")
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"response header {name} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"response header {name} must be non-negative")
    return parsed


class Esp32CameraClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 2.0,
        *,
        session: requests.Session | None = None,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._base_url = base_url.rstrip("/")
        if not self._base_url:
            raise ValueError("base_url must not be empty")
        self._timeout_s = timeout_s
        self._session = session or requests.Session()

    def status(self) -> dict[str, Any]:
        response = self._session.get(
            f"{self._base_url}/status", timeout=self._timeout_s
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("status response must be a JSON object")
        return payload

    def capture(self) -> CameraFrame:
        response = self._session.get(
            f"{self._base_url}/capture.pgm", timeout=self._timeout_s
        )
        response.raise_for_status()
        exposure_raw = response.headers.get("X-Exposure")
        exposure = None if exposure_raw in (None, "") else int(exposure_raw)
        return CameraFrame(
            frame_id=_required_header(response.headers, "X-Frame-Id"),
            timestamp_us=_required_header(response.headers, "X-Timestamp-Us"),
            image=parse_pgm(response.content),
            exposure=exposure,
        )
