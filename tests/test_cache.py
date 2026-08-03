from __future__ import annotations

import shutil
from pathlib import Path

from modpack_solver.metadata.cache import cache_raw_response, load_json, save_json


def test_cache_save_load_round_trip() -> None:
    payload = {"project_id": "P7dR8mSH", "versions": [1, 2, 3]}
    test_root = Path(".test-artifacts") / "cache_round_trip"
    if test_root.exists():
        shutil.rmtree(test_root)
    json_path = test_root / "cache" / "payload.json"

    save_json(json_path, payload)
    loaded = load_json(json_path)

    assert loaded == payload


def test_cache_raw_response_returns_written_path() -> None:
    payload = {"slug": "fabric-api"}
    test_root = Path(".test-artifacts") / "cache_raw_response"
    if test_root.exists():
        shutil.rmtree(test_root)

    cache_path = cache_raw_response(test_root / "responses", "fabric api", payload)

    assert cache_path.exists()
    assert cache_path.name == "fabric_api.json"
    assert load_json(cache_path) == payload
