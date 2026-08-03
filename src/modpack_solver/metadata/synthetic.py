"""Synthetic JSON fixture loading helpers."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from modpack_solver.models import SyntheticCase


def load_synthetic_case(path: str | Path) -> SyntheticCase:
    """Load one synthetic fixture file into normalized internal models."""

    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    try:
        return SyntheticCase.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid synthetic fixture at '{fixture_path}': {exc}") from exc


def load_synthetic_cases(directory: str | Path) -> list[SyntheticCase]:
    """Load every synthetic JSON fixture in a directory in sorted order."""

    fixture_dir = Path(directory)
    return [load_synthetic_case(path) for path in sorted(fixture_dir.glob("*.json"))]
