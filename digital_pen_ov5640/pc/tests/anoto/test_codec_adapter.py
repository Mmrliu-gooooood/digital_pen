from __future__ import annotations

import microdots
import numpy as np
import pytest

from digital_pen.anoto.codec_adapter import (
    AnotoCodecAdapter,
    AnotoDecodeError,
    direction_bits,
)
from digital_pen.types import DotDirection


def _bits_to_directions(bits: np.ndarray) -> np.ndarray:
    return bits[..., 0] + 2 * bits[..., 1]


def test_direction_mapping_matches_generator_and_rust_reader() -> None:
    assert direction_bits(DotDirection.UP) == (0, 0)
    assert direction_bits(DotDirection.LEFT) == (1, 0)
    assert direction_bits(DotDirection.RIGHT) == (0, 1)
    assert direction_bits(DotDirection.DOWN) == (1, 1)


def test_adapter_decodes_generator_window() -> None:
    section = (10, 2)
    bits = microdots.anoto_6x6_a4_fixed.encode_bitmatrix(
        (20, 20), section=section
    )
    window = _bits_to_directions(bits[7:13, 9:15])

    assert AnotoCodecAdapter().decode_window(window, section) == (9, 7)


def test_adapter_rejects_wrong_section_and_missing_values() -> None:
    bits = microdots.anoto_6x6_a4_fixed.encode_bitmatrix((10, 10), section=(4, 3))
    window = _bits_to_directions(bits[:6, :6]).astype(np.float64)

    with pytest.raises(AnotoDecodeError, match="does not match"):
        AnotoCodecAdapter().decode_window(window, (4, 2))

    window[2, 3] = np.nan
    with pytest.raises(ValueError, match="missing"):
        AnotoCodecAdapter().decode_window(window, (4, 3))


def test_adapter_compares_section_coordinates_modulo_mns_length() -> None:
    bits = microdots.anoto_6x6_a4_fixed.encode_bitmatrix(
        (6, 6), section=(64, -1)
    )
    window = _bits_to_directions(bits)

    assert AnotoCodecAdapter().decode_window(window, (64, -1)) == (0, 0)


def test_adapter_rejects_huge_position_before_section_integration() -> None:
    class DangerousCodec:
        mns_length = 63

        def decode_position(self, bits: np.ndarray) -> tuple[int, int]:
            return (100_000_000, 0)

        def decode_section(self, bits: np.ndarray, pos: tuple[int, int]):
            raise AssertionError("expensive section integration was called")

    with pytest.raises(AnotoDecodeError, match="safe section validation"):
        AnotoCodecAdapter(DangerousCodec()).decode_window(
            np.zeros((6, 6), dtype=np.int8),
            (0, 0),
        )
