"""Basic, read-only support for Modrinth ``.mrpack`` manifests."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import unquote, urlparse
from zipfile import BadZipFile, ZipFile

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ImportedModpackFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    hashes: dict[str, str] = Field(default_factory=dict)
    downloads: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    project_id: str | None = None
    version_id: str | None = None


class ImportedModpack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_path: str | None = None
    name: str
    version_id: str | None = None
    minecraft_version: str | None = None
    loader: str | None = None
    loader_version: str | None = None
    files: list[ImportedModpackFile] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)
    version_ids: list[str] = Field(default_factory=list)


def extract_modrinth_ids_from_downloads(
    downloads: Sequence[str],
) -> tuple[str | None, str | None]:
    """Extract project/version IDs from standard Modrinth CDN download URLs."""

    for download in downloads:
        parsed = urlparse(download)
        host = (parsed.hostname or "").lower()
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if host.endswith("modrinth.com") and len(parts) >= 5 and parts[0] == "data" and parts[2] == "versions":
            return parts[1], parts[3]
    return None, None


def read_mrpack(path: str | Path) -> ImportedModpack:
    """Read ``modrinth.index.json`` without downloading or installing files."""

    archive_path = Path(path)
    if not archive_path.exists():
        raise FileNotFoundError(f".mrpack archive '{archive_path}' was not found.")

    try:
        with ZipFile(archive_path) as archive:
            try:
                raw_index = archive.read("modrinth.index.json")
            except KeyError as exc:
                raise ValueError(
                    f".mrpack archive '{archive_path}' does not contain modrinth.index.json."
                ) from exc
    except BadZipFile as exc:
        raise ValueError(f".mrpack archive '{archive_path}' is not a valid ZIP archive.") from exc

    try:
        payload = json.loads(raw_index.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"modrinth.index.json in '{archive_path}' is not valid UTF-8 JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("modrinth.index.json must contain a JSON object.")

    dependencies = payload.get("dependencies") or {}
    if not isinstance(dependencies, dict):
        raise ValueError("modrinth.index.json 'dependencies' must be an object.")

    loader, loader_version = _extract_loader(dependencies)
    imported_files: list[ImportedModpackFile] = []
    project_ids: list[str] = []
    version_ids: list[str] = []
    for index, raw_file in enumerate(payload.get("files") or []):
        if not isinstance(raw_file, dict):
            raise ValueError(f"modrinth.index.json file entry {index} must be an object.")
        downloads = list(raw_file.get("downloads") or [])
        project_id, version_id = extract_modrinth_ids_from_downloads(downloads)
        try:
            imported = ImportedModpackFile(
                path=raw_file["path"],
                hashes=dict(raw_file.get("hashes") or {}),
                downloads=downloads,
                env=dict(raw_file.get("env") or {}),
                project_id=project_id,
                version_id=version_id,
            )
        except (KeyError, ValidationError) as exc:
            raise ValueError(f"Invalid .mrpack file entry at index {index}: {exc}") from exc
        imported_files.append(imported)
        if project_id and project_id not in project_ids:
            project_ids.append(project_id)
        if version_id and version_id not in version_ids:
            version_ids.append(version_id)

    name = str(payload.get("name") or archive_path.stem).strip()
    if not name:
        raise ValueError("modrinth.index.json must provide a nonempty pack name.")
    return ImportedModpack(
        source_type="mrpack",
        source_path=str(archive_path),
        name=name,
        version_id=_optional_text(payload.get("versionId") or payload.get("version_id")),
        minecraft_version=_optional_text(dependencies.get("minecraft")),
        loader=loader,
        loader_version=loader_version,
        files=imported_files,
        project_ids=project_ids,
        version_ids=version_ids,
    )


def _extract_loader(dependencies: dict) -> tuple[str | None, str | None]:
    known_loaders = (
        ("fabric-loader", "fabric"),
        ("quilt-loader", "quilt"),
        ("neoforge", "neoforge"),
        ("forge", "forge"),
    )
    for dependency_key, loader_name in known_loaders:
        if dependency_key in dependencies:
            return loader_name, _optional_text(dependencies[dependency_key])
    return None, None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
