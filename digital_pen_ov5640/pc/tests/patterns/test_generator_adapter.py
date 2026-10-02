from __future__ import annotations

import json
from pathlib import Path

import pytest


def _adapter_api():
    try:
        from tools.patterns.generator_adapter import (
            PatternConfigError,
            generate_pattern,
            load_pattern_profile,
        )
    except ModuleNotFoundError:
        pytest.fail("generator_adapter is not implemented")
    return PatternConfigError, generate_pattern, load_pattern_profile


def _write_config(path: Path, *, right_color: str = "#000000") -> None:
    path.write_text(
        f"""
generator:
  root: D:/ESP32_project/AnotoPdfGenerator/AnotoPdfGenerator-main
profiles:
  A:
    page_id: debug-a
    dpi: 600
    grid_spacing_mm: 3.5278
    offset_mm: 1.0583
    dot_radius_mm: 0.3528
    colors:
      up: '#000000'
      down: '#000000'
      left: '#000000'
      right: '{right_color}'
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_profile_rejects_a_non_black_direction_color(tmp_path: Path) -> None:
    PatternConfigError, _, load_pattern_profile = _adapter_api()
    config_path = tmp_path / "pattern.yaml"
    _write_config(config_path, right_color="#ff0000")

    with pytest.raises(PatternConfigError, match="black"):
        load_pattern_profile(config_path, "A")


def test_generate_pattern_preserves_matrix_and_writes_monochrome_pdf(
    tmp_path: Path,
) -> None:
    _, generate_pattern, _ = _adapter_api()
    config_path = tmp_path / "pattern.yaml"
    _write_config(config_path)

    matrix = [
        [[[0, 0], [1, 0]], [[0, 1], [1, 1]]],
    ][0]

    def fake_generator(command: list[str], cwd: Path, env: dict[str, str]) -> None:
        assert env["CARGO_HOME"].startswith(str(tmp_path.parent)) is False
        rows, cols, section_u, section_v = map(int, command[-4:])
        assert (rows, cols, section_u, section_v) == (2, 2, 10, 2)
        output = cwd / "output"
        output.mkdir()
        (output / "G__2__2__10__2.json").write_text(
            json.dumps(matrix), encoding="utf-8"
        )

    manifest_path = Path(
        generate_pattern(
            "A",
            rows=2,
            cols=2,
            section_u=10,
            section_v=2,
            output_dir=str(tmp_path / "artifacts"),
            config_path=config_path,
            runner=fake_generator,
        )
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    copied_matrix = Path(manifest["matrix_json"])
    pdf_path = Path(manifest["pdf_path"])

    assert copied_matrix.is_absolute()
    assert json.loads(copied_matrix.read_text(encoding="utf-8")) == matrix
    assert manifest["page_id"] == "debug-a"
    assert manifest["section_u"] == 10
    assert manifest["section_v"] == 2
    assert manifest["rows"] == 2
    assert manifest["cols"] == 2
    assert manifest["grid_spacing_mm"] == pytest.approx(3.5278)
    assert manifest["dot_radius_mm"] == pytest.approx(0.3528)
    assert manifest["offset_mm"] == pytest.approx(1.0583)
    assert pdf_path.read_bytes().startswith(b"%PDF-1.4")
    assert b"0 g" in pdf_path.read_bytes()
    assert b" rg" not in pdf_path.read_bytes()
