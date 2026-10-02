from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import microdots
import numpy as np
from microdots.exceptions import DecodingError


@dataclass(frozen=True)
class VerificationResult:
    checked: int
    passed: int
    failed: int
    failures: tuple[str, ...]


def _load_json_object(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError("manifest must be a JSON object")
    return loaded


def _resolve_manifest_path(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path.resolve()


def verify_manifest(
    manifest_path: str | Path,
    *,
    samples: int = 1000,
    seed: int = 0,
) -> VerificationResult:
    if samples <= 0:
        raise ValueError("samples must be positive")
    manifest_path = Path(manifest_path).resolve()
    manifest = _load_json_object(manifest_path)
    matrix_path = _resolve_manifest_path(manifest_path, str(manifest["matrix_json"]))
    matrix = np.asarray(json.loads(matrix_path.read_text(encoding="utf-8")), dtype=np.int8)
    rows = int(manifest["rows"])
    cols = int(manifest["cols"])
    if matrix.shape != (rows, cols, 2):
        raise ValueError(
            f"matrix shape {matrix.shape} does not match manifest {(rows, cols, 2)}"
        )
    if rows < 6 or cols < 6:
        raise ValueError("matrix must contain at least one 6x6 window")
    if not np.isin(matrix, (0, 1)).all():
        raise ValueError("matrix values must be bits")

    expected_section = (int(manifest["section_u"]), int(manifest["section_v"]))
    rng = random.Random(seed)
    failures: list[str] = []
    passed = 0
    codec = microdots.anoto_6x6_a4_fixed
    for sample_index in range(samples):
        row = rng.randint(0, rows - 6)
        col = rng.randint(0, cols - 6)
        window = matrix[row : row + 6, col : col + 6]
        try:
            position = tuple(int(value) for value in codec.decode_position(window))
            section = tuple(
                int(value) for value in codec.decode_section(window, pos=position)
            )
        except DecodingError as exc:
            failures.append(f"sample {sample_index} at ({row},{col}): {exc}")
            continue
        expected_position = (col, row)
        if position != expected_position or section != expected_section:
            failures.append(
                f"sample {sample_index} at ({row},{col}): "
                f"position={position}, section={section}"
            )
            continue
        passed += 1
    return VerificationResult(
        checked=samples,
        passed=passed,
        failed=samples - passed,
        failures=tuple(failures),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an Anoto pattern manifest")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    result = verify_manifest(args.manifest, samples=args.samples, seed=args.seed)
    print(f"{result.passed}/{result.checked} windows decoded correctly")
    if result.failed:
        for failure in result.failures[:10]:
            print(f"FAIL: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
