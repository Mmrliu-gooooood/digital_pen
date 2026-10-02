"""Anoto direction-matrix and coordinate decoding helpers."""

from digital_pen.anoto.codec_adapter import (
    DIRECTION_VECTORS,
    AnotoCodecAdapter,
    AnotoDecodeError,
    direction_bits,
    directions_to_bits,
)
from digital_pen.anoto.matrix_builder import (
    build_direction_matrices,
    build_direction_matrix,
)
from digital_pen.anoto.window_consensus import (
    ConsensusResult,
    WindowDecode,
    decode_consensus,
    decode_oriented_consensus,
    decode_windows,
    transform_direction_matrix,
)

__all__ = [
    "AnotoCodecAdapter",
    "AnotoDecodeError",
    "ConsensusResult",
    "DIRECTION_VECTORS",
    "WindowDecode",
    "build_direction_matrices",
    "build_direction_matrix",
    "decode_consensus",
    "decode_oriented_consensus",
    "decode_windows",
    "direction_bits",
    "directions_to_bits",
    "transform_direction_matrix",
]
