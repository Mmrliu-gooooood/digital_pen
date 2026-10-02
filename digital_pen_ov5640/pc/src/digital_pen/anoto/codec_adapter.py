"""Thin, image-free adapter around the py-microdots Anoto codec."""

from __future__ import annotations

from typing import Any

import numpy as np

from digital_pen.types import DotDirection

DIRECTION_BITS = np.asarray(
    [
        (0, 0),  # UP
        (1, 0),  # LEFT
        (0, 1),  # RIGHT
        (1, 1),  # DOWN
    ],
    dtype=np.int8,
)
DIRECTION_VECTORS = {
    DotDirection.UP: (0, -1),
    DotDirection.LEFT: (-1, 0),
    DotDirection.RIGHT: (1, 0),
    DotDirection.DOWN: (0, 1),
}


class AnotoDecodeError(ValueError):
    """Raised when a direction window is invalid or cannot be decoded."""


def directions_to_bits(directions: np.ndarray) -> np.ndarray:
    """Convert a direction matrix to the ``(rows, cols, 2)`` codec format."""
    values = np.asarray(directions)
    if values.ndim != 2:
        raise ValueError("directions must be a 2D matrix")
    if not np.issubdtype(values.dtype, np.number):
        raise ValueError("directions must contain numeric direction values")
    if not np.all(np.isfinite(values)):
        raise ValueError("directions must not contain missing values")
    integral = values.astype(np.int64)
    if not np.array_equal(values, integral) or not np.isin(integral, range(4)).all():
        raise ValueError("directions must contain only UP, LEFT, RIGHT, or DOWN")
    return DIRECTION_BITS[integral]


class AnotoCodecAdapter:
    """Decode canonical direction windows while hiding py-microdots details."""

    def __init__(
        self,
        codec: Any | None = None,
        *,
        max_direct_section_position: int = 100_000,
    ) -> None:
        if codec is None:
            try:
                import microdots
            except ModuleNotFoundError as error:
                raise RuntimeError(
                    "Anoto decoding requires the 'microdots' package; "
                    "install the digital-pen codec dependency"
                ) from error
            codec = microdots.anoto_6x6_a4_fixed
        self._codec = codec
        self._max_direct_section_position = max_direct_section_position

    def decode_window(
        self,
        directions: np.ndarray,
        section: tuple[int, int],
    ) -> tuple[int, int]:
        """Decode one complete 6x6 window and verify its expected section."""
        values = np.asarray(directions)
        if values.shape != (6, 6):
            raise ValueError("directions must have shape (6, 6)")
        if len(section) != 2:
            raise ValueError("section must contain exactly two coordinates")
        position = self.decode_position(values)
        self.validate_section(values, position, section)
        return position

    def decode_position(self, directions: np.ndarray) -> tuple[int, int]:
        """Decode position without the potentially expensive section lookup."""
        values = np.asarray(directions)
        if values.shape != (6, 6):
            raise ValueError("directions must have shape (6, 6)")
        bits = directions_to_bits(values)
        try:
            position = tuple(int(value) for value in self._codec.decode_position(bits))
        except (ValueError, IndexError) as error:
            raise AnotoDecodeError(str(error)) from error
        return position

    def validate_section(
        self,
        directions: np.ndarray,
        position: tuple[int, int],
        section: tuple[int, int],
    ) -> None:
        """Verify a decoded position against the expected section identity."""
        values = np.asarray(directions)
        if values.shape != (6, 6):
            raise ValueError("directions must have shape (6, 6)")
        if len(section) != 2:
            raise ValueError("section must contain exactly two coordinates")
        if min(position) < 0 or max(position) > self._max_direct_section_position:
            raise AnotoDecodeError(
                "decoded position is too large for safe section validation; "
                "use manifest bounds before validating the section"
            )
        bits = directions_to_bits(values)
        try:
            decoded_section = tuple(
                int(value)
                for value in self._codec.decode_section(bits, pos=position)
            )
        except (ValueError, IndexError) as error:
            raise AnotoDecodeError(str(error)) from error
        modulus = int(getattr(self._codec, "mns_length", 63))
        expected_section = tuple(int(value) % modulus for value in section)
        if decoded_section != expected_section:
            raise AnotoDecodeError(
                f"decoded section {decoded_section} does not match {expected_section}"
            )


def direction_bits(direction: DotDirection) -> tuple[int, int]:
    """Return the protocol bits for one public direction enum value."""
    bits = DIRECTION_BITS[int(direction)]
    return int(bits[0]), int(bits[1])
