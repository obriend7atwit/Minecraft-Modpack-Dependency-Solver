"""Deterministic raw Modrinth metadata cache with explicit offline/live modes."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from modpack_solver.metadata.modrinth import MODRINTH_BASE_URL, USER_AGENT
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.models import SyntheticCase


class ModrinthCacheMode(str, Enum):
    OFFLINE = "offline"
    LIVE = "live"


def cache_resource_path(
    cache_dir: str | Path,
    category: str,
    resource_id: str,
) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", resource_id.strip())
    if not safe_id:
        raise ValueError("Cache resource ID cannot be empty.")
    return Path(cache_dir) / "raw" / category / f"{safe_id}.json"


def load_cached_json(path: str | Path) -> Any:
    cache_path = Path(path)
    if not cache_path.exists():
        raise FileNotFoundError(f"Cached metadata '{cache_path}' was not found.")
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cached metadata '{cache_path}' is not valid JSON.") from exc


def save_cached_json(path: str | Path, data: Any) -> Path:
    cache_path = Path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return cache_path


def fetch_or_load_project(
    project_id_or_slug: str,
    *,
    cache_dir: str | Path,
    mode: ModrinthCacheMode,
    force_refresh: bool = False,
) -> dict:
    return _fetch_or_load(
        category="projects",
        resource_id=project_id_or_slug,
        api_path=f"/project/{project_id_or_slug}",
        cache_dir=cache_dir,
        mode=mode,
        expected_type=dict,
        force_refresh=force_refresh,
    )


def fetch_or_load_project_versions(
    project_id_or_slug: str,
    *,
    cache_dir: str | Path,
    mode: ModrinthCacheMode,
    force_refresh: bool = False,
) -> list[dict]:
    return _fetch_or_load(
        category="versions",
        resource_id=project_id_or_slug,
        api_path=f"/project/{project_id_or_slug}/version",
        cache_dir=cache_dir,
        mode=mode,
        expected_type=list,
        force_refresh=force_refresh,
        params={"include_changelog": "false"},
    )


def fetch_or_load_version(
    version_id: str,
    *,
    cache_dir: str | Path,
    mode: ModrinthCacheMode,
    force_refresh: bool = False,
) -> dict:
    return _fetch_or_load(
        category="version_details",
        resource_id=version_id,
        api_path=f"/version/{version_id}",
        cache_dir=cache_dir,
        mode=mode,
        expected_type=dict,
        force_refresh=force_refresh,
    )


def build_case_from_modrinth_modpack(
    modpack_slug_or_id: str,
    *,
    minecraft_version: str | None = None,
    loader: str | None = None,
    cache_dir: str | Path,
    mode: ModrinthCacheMode,
) -> SyntheticCase:
    """Load a normalized cached pack case.

    Modrinth's project endpoint does not expose a pack's member mods. A cached
    normalized case, usually prepared from an ``.mrpack`` manifest, is therefore
    required. Live mode may cache project metadata but never downloads pack files.
    """

    key = re.sub(r"[^A-Za-z0-9._-]+", "_", modpack_slug_or_id.strip())
    normalized_path = Path(cache_dir) / "normalized" / "cases" / f"{key}.json"
    if normalized_path.exists():
        case = load_synthetic_case(normalized_path)
        updates = {}
        if minecraft_version:
            updates["minecraft_version"] = minecraft_version
        if loader:
            updates["loader"] = loader
        if updates:
            case = case.model_copy(
                update={"config": case.config.model_copy(update=updates)},
                deep=True,
            )
        return case

    if mode == ModrinthCacheMode.LIVE:
        fetch_or_load_project(modpack_slug_or_id, cache_dir=cache_dir, mode=mode)
        fetch_or_load_project_versions(modpack_slug_or_id, cache_dir=cache_dir, mode=mode)
    raise FileNotFoundError(
        f"No normalized cached case exists for Modrinth modpack '{modpack_slug_or_id}'. "
        "Import its local .mrpack manifest first; pack files are not downloaded automatically."
    )


def _fetch_or_load(
    *,
    category: str,
    resource_id: str,
    api_path: str,
    cache_dir: str | Path,
    mode: ModrinthCacheMode,
    expected_type: type,
    force_refresh: bool,
    params: dict[str, str] | None = None,
):
    mode = ModrinthCacheMode(mode)
    cache_path = cache_resource_path(cache_dir, category, resource_id)
    if cache_path.exists() and not force_refresh:
        payload = load_cached_json(cache_path)
    elif mode == ModrinthCacheMode.OFFLINE:
        raise FileNotFoundError(
            f"No cached Modrinth {category.rstrip('s')} metadata for '{resource_id}' at '{cache_path}'."
        )
    else:
        payload = _fetch_json(api_path, params=params)
        save_cached_json(cache_path, payload)
        _update_collection_index(
            cache_dir=cache_dir,
            category=category,
            resource_id=resource_id,
            api_url=f"{MODRINTH_BASE_URL}{api_path}",
            cache_path=cache_path,
        )

    if not isinstance(payload, expected_type):
        raise ValueError(
            f"Cached Modrinth {category} response for '{resource_id}' must be a {expected_type.__name__}."
        )
    return payload


def _fetch_json(api_path: str, params: dict[str, str] | None = None) -> Any:
    with httpx.Client(
        base_url=MODRINTH_BASE_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=20.0,
    ) as client:
        response = client.get(api_path, params=params)
        response.raise_for_status()
        return response.json()


def _update_collection_index(
    *,
    cache_dir: str | Path,
    category: str,
    resource_id: str,
    api_url: str,
    cache_path: Path,
) -> None:
    index_path = Path(cache_dir) / "collection_index.json"
    if index_path.exists():
        payload = load_cached_json(index_path)
        if not isinstance(payload, dict):
            payload = {}
    else:
        payload = {}
    entries = payload.setdefault("entries", {})
    entry_key = f"{category}:{resource_id}"
    entries[entry_key] = {
        "category": category,
        "resource_id": resource_id,
        "api_url": api_url,
        "cache_path": str(cache_path),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    save_cached_json(index_path, payload)
