import json
from zipfile import ZipFile

import pytest

from modpack_solver.importers.mrpack_importer import (
    extract_modrinth_ids_from_downloads,
    read_mrpack,
)


def _write_mrpack(path, payload=None):
    payload = payload or {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": "demo-1.0",
        "name": "Demo Pack",
        "dependencies": {"minecraft": "1.20.1", "fabric-loader": "0.15.0"},
        "files": [
            {
                "path": "mods/example.jar",
                "hashes": {"sha1": "abc"},
                "downloads": ["https://cdn.modrinth.com/data/project123/versions/version456/example.jar"],
                "env": {"client": "required", "server": "required"},
            }
        ],
    }
    with ZipFile(path, "w") as archive:
        archive.writestr("modrinth.index.json", json.dumps(payload))


def test_valid_mrpack_extracts_manifest_without_downloading(tmp_path, monkeypatch):
    path = tmp_path / "demo.mrpack"
    _write_mrpack(path)
    imported = read_mrpack(path)
    assert imported.name == "Demo Pack"
    assert imported.minecraft_version == "1.20.1"
    assert imported.loader == "fabric"
    assert imported.loader_version == "0.15.0"
    assert imported.project_ids == ["project123"]
    assert imported.version_ids == ["version456"]
    assert imported.files[0].path == "mods/example.jar"


def test_extract_modrinth_ids_returns_none_for_unrelated_url():
    assert extract_modrinth_ids_from_downloads(["https://example.com/file.jar"]) == (None, None)


def test_mrpack_missing_index_fails_clearly(tmp_path):
    path = tmp_path / "missing.mrpack"
    with ZipFile(path, "w") as archive:
        archive.writestr("other.json", "{}")
    with pytest.raises(ValueError, match="modrinth.index.json"):
        read_mrpack(path)


def test_mrpack_invalid_json_fails_clearly(tmp_path):
    path = tmp_path / "invalid.mrpack"
    with ZipFile(path, "w") as archive:
        archive.writestr("modrinth.index.json", "not-json")
    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        read_mrpack(path)


def test_mrpack_invalid_zip_fails_clearly(tmp_path):
    path = tmp_path / "invalid.mrpack"
    path.write_text("not a zip", encoding="utf-8")
    with pytest.raises(ValueError, match="valid ZIP"):
        read_mrpack(path)
