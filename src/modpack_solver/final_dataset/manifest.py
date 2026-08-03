"""Final dataset manifest loading and path resolution."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from modpack_solver.final_dataset.models import FinalDatasetCaseSpec, FinalDatasetManifest


def load_final_dataset_manifest(path: str | Path) -> FinalDatasetManifest:
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Final dataset manifest '{manifest_path}' was not found.")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Final dataset manifest '{manifest_path}' is not valid JSON.") from exc
    try:
        return FinalDatasetManifest.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid final dataset manifest '{manifest_path}': {exc}") from exc


def resolve_final_case_path(
    case: FinalDatasetCaseSpec,
    manifest_path: str | Path,
) -> Path:
    fixture_path = Path(case.fixture_path)
    if fixture_path.is_absolute():
        return fixture_path
    return (Path(manifest_path).resolve().parent / fixture_path).resolve()


def resolve_optional_manifest_path(value: str | None, manifest_path: str | Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else (Path(manifest_path).resolve().parent / path).resolve()
