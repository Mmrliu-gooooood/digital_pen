from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "pc" / "configs" / "pattern.yaml"
Runner = Callable[[list[str], Path, dict[str, str]], None]


class PatternConfigError(ValueError):
    """Raised when a pattern profile cannot produce monochrome Anoto paper."""


@dataclass(frozen=True)
class PatternProfile:
    name: str
    page_id: str
    dpi: int
    grid_spacing_mm: float
    offset_mm: float
    dot_radius_mm: float
    colors: dict[str, str]
    generator_root: Path


@dataclass(frozen=True)
class PatternManifest:
    page_id: str
    section_u: int
    section_v: int
    rows: int
    cols: int
    grid_spacing_mm: float
    dot_radius_mm: float
    offset_mm: float
    matrix_json: str
    pdf_path: str


def _read_config(config_path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PatternConfigError(f"cannot read pattern config: {exc}") from exc
    if not isinstance(loaded, dict):
        raise PatternConfigError("pattern config must be a YAML mapping")
    return loaded


def load_pattern_profile(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    profile_name: str = "A",
) -> PatternProfile:
    config_path = Path(config_path).resolve()
    config = _read_config(config_path)
    profiles = config.get("profiles")
    if not isinstance(profiles, dict) or profile_name not in profiles:
        raise PatternConfigError(f"unknown pattern profile: {profile_name}")
    profile = profiles[profile_name]
    generator = config.get("generator", {})
    if not isinstance(profile, dict) or not isinstance(generator, dict):
        raise PatternConfigError("generator and profile entries must be mappings")

    colors = profile.get("colors")
    required_directions = {"up", "down", "left", "right"}
    if not isinstance(colors, dict) or set(colors) != required_directions:
        raise PatternConfigError("profile must define all four direction colors")
    normalized_colors = {name: str(value).lower() for name, value in colors.items()}
    if any(color not in {"#000000", "#000"} for color in normalized_colors.values()):
        raise PatternConfigError("all direction colors must be black")

    generator_root = Path(str(generator.get("root", "")))
    if not generator_root.is_absolute():
        generator_root = (config_path.parent / generator_root).resolve()

    try:
        result = PatternProfile(
            name=profile_name,
            page_id=str(profile["page_id"]),
            dpi=int(profile["dpi"]),
            grid_spacing_mm=float(profile["grid_spacing_mm"]),
            offset_mm=float(profile["offset_mm"]),
            dot_radius_mm=float(profile["dot_radius_mm"]),
            colors=normalized_colors,
            generator_root=generator_root,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PatternConfigError(f"invalid profile {profile_name}: {exc}") from exc

    if result.dpi <= 0:
        raise PatternConfigError("dpi must be positive")
    if result.grid_spacing_mm <= 0 or result.dot_radius_mm <= 0:
        raise PatternConfigError("grid spacing and dot radius must be positive")
    if not 0 < result.offset_mm < result.grid_spacing_mm / 2:
        raise PatternConfigError("offset must be positive and below half the grid spacing")
    return result


def _validate_matrix(matrix: Any, rows: int, cols: int) -> list[list[list[int]]]:
    if not isinstance(matrix, list) or len(matrix) != rows:
        raise PatternConfigError(f"generator matrix must have {rows} rows")
    for row in matrix:
        if not isinstance(row, list) or len(row) != cols:
            raise PatternConfigError(f"generator matrix must have {cols} columns")
        for pair in row:
            if not isinstance(pair, list) or len(pair) != 2:
                raise PatternConfigError("each generator matrix cell must contain two bits")
            if any(bit not in (0, 1) for bit in pair):
                raise PatternConfigError("generator matrix values must be bits")
    return matrix


def _circle_path(x: float, y: float, radius: float) -> str:
    control = radius * 0.5522847498
    return (
        f"{x + radius:.4f} {y:.4f} m\n"
        f"{x + radius:.4f} {y + control:.4f} "
        f"{x + control:.4f} {y + radius:.4f} {x:.4f} {y + radius:.4f} c\n"
        f"{x - control:.4f} {y + radius:.4f} "
        f"{x - radius:.4f} {y + control:.4f} {x - radius:.4f} {y:.4f} c\n"
        f"{x - radius:.4f} {y - control:.4f} "
        f"{x - control:.4f} {y - radius:.4f} {x:.4f} {y - radius:.4f} c\n"
        f"{x + control:.4f} {y - radius:.4f} "
        f"{x + radius:.4f} {y - control:.4f} {x + radius:.4f} {y:.4f} c\n"
        "f\n"
    )


def _write_pdf(objects: list[bytes], output_path: Path) -> None:
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{index} 0 obj\n".encode("ascii"))
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    output_path.write_bytes(document)


def render_monochrome_pdf(
    matrix: list[list[list[int]]], profile: PatternProfile, output_path: Path
) -> None:
    points_per_mm = 72.0 / 25.4
    page_width = 210.0 * points_per_mm
    page_height = 297.0 * points_per_mm
    spacing = profile.grid_spacing_mm * points_per_mm
    offset = profile.offset_mm * points_per_mm
    radius = profile.dot_radius_mm * points_per_mm
    rows = len(matrix)
    cols = len(matrix[0])
    grid_width = (cols - 1) * spacing
    grid_height = (rows - 1) * spacing
    minimum_margin = 5.0 * points_per_mm
    if grid_width > page_width - 2 * minimum_margin:
        raise PatternConfigError("pattern is wider than an A4 page")
    if grid_height > page_height - 2 * minimum_margin:
        raise PatternConfigError("pattern is taller than an A4 page")

    origin_x = (page_width - grid_width) / 2
    origin_y = (page_height - grid_height) / 2
    content = ["0 g\n"]
    direction_offsets = {
        (0, 0): (0.0, offset),
        (1, 0): (-offset, 0.0),
        (0, 1): (offset, 0.0),
        (1, 1): (0.0, -offset),
    }
    for row_index, row in enumerate(matrix):
        for col_index, pair in enumerate(row):
            dx, dy = direction_offsets[(pair[0], pair[1])]
            x = origin_x + col_index * spacing + dx
            y = origin_y + row_index * spacing + dy
            content.append(_circle_path(x, y, radius))
    stream = "".join(content).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
            f"{page_width:.4f} {page_height:.4f}] /Contents 4 0 R >>"
        ).encode("ascii"),
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
        + stream
        + b"endstream",
    ]
    _write_pdf(objects, output_path)


def _default_runner(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def generate_pattern(
    profile_name: str,
    rows: int,
    cols: int,
    section_u: int,
    section_v: int,
    output_dir: str,
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    runner: Runner | None = None,
) -> str:
    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive")
    profile = load_pattern_profile(config_path, profile_name)
    cargo_manifest = profile.generator_root / "Cargo.toml"
    if runner is None and not cargo_manifest.is_file():
        raise FileNotFoundError(f"AnotoPdfGenerator not found: {cargo_manifest}")

    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    temp_root = PROJECT_ROOT / ".tmp"
    cargo_home = PROJECT_ROOT / ".cache" / "cargo-home"
    cargo_target = PROJECT_ROOT / ".cargo-target"
    for directory in (temp_root, cargo_home, cargo_target):
        directory.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["CARGO_HOME"] = str(cargo_home)
    env["CARGO_TARGET_DIR"] = str(cargo_target)
    command = [
        "cargo",
        "run",
        "--quiet",
        "--manifest-path",
        str(cargo_manifest),
        "--bin",
        "generator_cli",
        "--",
        "-g",
        str(rows),
        str(cols),
        str(section_u),
        str(section_v),
    ]
    actual_runner = runner or _default_runner
    with tempfile.TemporaryDirectory(prefix="anoto-generator-", dir=temp_root) as work:
        work_path = Path(work)
        actual_runner(command, work_path, env)
        generated_matrix = (
            work_path
            / "output"
            / f"G__{rows}__{cols}__{section_u}__{section_v}.json"
        )
        if not generated_matrix.is_file():
            raise FileNotFoundError(f"Generator did not create {generated_matrix.name}")
        matrix = _validate_matrix(
            json.loads(generated_matrix.read_text(encoding="utf-8")), rows, cols
        )

        stem = f"{profile.page_id}_{rows}x{cols}_s{section_u}_{section_v}"
        matrix_path = (output_path / f"{stem}.matrix.json").resolve()
        shutil.copyfile(generated_matrix, matrix_path)

    pdf_path = (output_path / f"{stem}.pdf").resolve()
    render_monochrome_pdf(matrix, profile, pdf_path)
    manifest = PatternManifest(
        page_id=profile.page_id,
        section_u=section_u,
        section_v=section_v,
        rows=rows,
        cols=cols,
        grid_spacing_mm=profile.grid_spacing_mm,
        dot_radius_mm=profile.dot_radius_mm,
        offset_mm=profile.offset_mm,
        matrix_json=str(matrix_path),
        pdf_path=str(pdf_path),
    )
    manifest_path = (output_path / f"{stem}.manifest.json").resolve()
    manifest_path.write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return str(manifest_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate monochrome Anoto paper")
    parser.add_argument("--profile", default="A")
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--cols", type=int, required=True)
    parser.add_argument("--section-u", type=int, default=10)
    parser.add_argument("--section-v", type=int, default=2)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()
    manifest = generate_pattern(
        args.profile,
        args.rows,
        args.cols,
        args.section_u,
        args.section_v,
        args.output_dir,
        config_path=args.config,
    )
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
