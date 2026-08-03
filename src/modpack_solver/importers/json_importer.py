"""Final-GUI wrapper for the project's existing JSON case format."""

from __future__ import annotations

import json
from pathlib import Path

from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.models import SyntheticCase


def load_case_json(path: str | Path) -> SyntheticCase:
    """Load a ``SyntheticCase``-compatible JSON file with readable errors."""

    case_path = Path(path)
    if not case_path.exists():
        raise FileNotFoundError(f"Modpack JSON file '{case_path}' was not found.")
    if not case_path.is_file():
        raise ValueError(f"Modpack JSON path '{case_path}' is not a file.")

    try:
        return load_synthetic_case(case_path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Modpack JSON file '{case_path}' is not valid JSON.") from exc
    except ValueError as exc:
        raise ValueError(f"Could not load modpack JSON '{case_path}': {exc}") from exc
