"""Simple file-based JSON cache helpers for early metadata work."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def save_json(path: str | Path, data: Any) -> None:
    """Write JSON to disk with deterministic pretty-printing."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_json(path: str | Path) -> Any:
    """Load JSON from disk using UTF-8 encoding."""

    input_path = Path(path)
    return json.loads(input_path.read_text(encoding="utf-8"))


def cache_raw_response(cache_dir: str | Path, name: str, data: Any) -> Path:
    """Persist a raw API response under a stable JSON file name."""

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "cache_entry"
    cache_path = Path(cache_dir) / f"{safe_name}.json"
    save_json(cache_path, data)
    return cache_path
