"""Small deterministic export helpers for final dataset artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_pretty_json(path: str | Path, data: Any) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return output_path
