from __future__ import annotations

import json
from pathlib import Path

import microdots
import pytest


def _verify_api():
    try:
        from tools.patterns.verify_codec import verify_manifest
    except ModuleNotFoundError:
        pytest.fail("verify_codec is not implemented")
    return verify_manifest


def _write_manifest(tmp_path: Path, matrix: list, *, section: tuple[int, int]) -> Path:
    matrix_path = (tmp_path / "matrix.json").resolve()
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    manifest_path = (tmp_path / "manifest.json").resolve()
    manifest_path.write_text(
        json.dumps(
            {
                "page_id": "test-page",
                "section_u": section[0],
                "section_v": section[1],
                "rows": len(matrix),
                "cols": len(matrix[0]),
                "grid_spacing_mm": 3.5278,
                "dot_radius_mm": 0.3528,
                "offset_mm": 1.0583,
                "matrix_json": str(matrix_path),
                "pdf_path": str((tmp_path / "unused.pdf").resolve()),
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_verifier_accepts_generator_compatible_windows(tmp_path: Path) -> None:
    verify_manifest = _verify_api()
    section = (10, 2)
    matrix = microdots.anoto_6x6_a4_fixed.encode_bitmatrix(
        (20, 20), section=section
    ).tolist()
    manifest_path = _write_manifest(tmp_path, matrix, section=section)

    result = verify_manifest(manifest_path, samples=50, seed=20260827)

    assert result.checked == 50
    assert result.passed == 50
    assert result.failed == 0


def test_verifier_reports_invalid_windows(tmp_path: Path) -> None:
    verify_manifest = _verify_api()
    matrix = [[[[0, 0][i] for i in range(2)] for _ in range(12)] for _ in range(12)]
    manifest_path = _write_manifest(tmp_path, matrix, section=(10, 2))

    result = verify_manifest(manifest_path, samples=10, seed=7)

    assert result.checked == 10
    assert result.passed == 0
    assert result.failed == 10
