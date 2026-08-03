"""Modrinth access and normalization helpers for the Week 3 metadata layer."""

from __future__ import annotations

import json

import httpx

from modpack_solver.models import Dependency, DependencyType, MetadataSource, ModVersion


MODRINTH_BASE_URL = "https://api.modrinth.com/v2"
USER_AGENT = "minecraft-modpack-solver/0.1"


def normalize_modrinth_dependency(raw: dict) -> Dependency:
    """Normalize one Modrinth dependency object into the internal model."""

    dependency_type = _parse_dependency_type(raw.get("dependency_type"))
    target_mod_id = raw.get("project_id") or raw.get("file_name") or "unknown"

    return Dependency(
        target_mod_id=target_mod_id,
        dependency_type=dependency_type,
        target_version_id=raw.get("version_id"),
        raw_constraint=raw.get("version_requirement"),
        source=MetadataSource.MODRINTH,
    )


def normalize_modrinth_version(raw: dict) -> ModVersion:
    """Normalize one Modrinth version payload into the internal model."""

    dependencies = [
        normalize_modrinth_dependency(dependency)
        for dependency in raw.get("dependencies", [])
    ]

    return ModVersion(
        version_id=raw["id"],
        mod_id=raw["project_id"],
        version_number=raw["version_number"],
        game_versions=list(raw.get("game_versions", [])),
        loaders=list(raw.get("loaders", [])),
        version_type=raw.get("version_type"),
        dependencies=dependencies,
        source=MetadataSource.MODRINTH,
    )


def fetch_project_summary(project_slug: str, timeout: float = 10.0) -> dict[str, str]:
    """Fetch a small public summary for a Modrinth project."""

    with httpx.Client(
        base_url=MODRINTH_BASE_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    ) as client:
        response = client.get(f"/project/{project_slug}")
        response.raise_for_status()
        payload = response.json()

    return {
        "project_id": payload["id"],
        "slug": payload["slug"],
        "title": payload["title"],
        "project_type": payload["project_type"],
    }


def fetch_project_versions(
    project_id_or_slug: str,
    game_version: str | None = None,
    loader: str | None = None,
    timeout: float = 10.0,
) -> list[dict]:
    """Fetch raw Modrinth versions for a project, optionally filtered."""

    params: dict[str, str] = {"include_changelog": "false"}
    if game_version:
        params["game_versions"] = json.dumps([game_version])
    if loader:
        params["loaders"] = json.dumps([loader])

    with httpx.Client(
        base_url=MODRINTH_BASE_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    ) as client:
        response = client.get(f"/project/{project_id_or_slug}/version", params=params)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, list):
        raise ValueError("Expected a list of versions from Modrinth.")
    return payload


def get_normalized_project_versions(
    project_id_or_slug: str,
    game_version: str | None = None,
    loader: str | None = None,
    timeout: float = 10.0,
) -> list[ModVersion]:
    """Fetch and normalize Modrinth versions for one project."""

    return [
        normalize_modrinth_version(raw_version)
        for raw_version in fetch_project_versions(
            project_id_or_slug=project_id_or_slug,
            game_version=game_version,
            loader=loader,
            timeout=timeout,
        )
    ]


def check_modrinth_fabric_api_access(timeout: float = 10.0) -> dict[str, str]:
    """Fetch a minimal summary for Modrinth's `fabric-api` project."""

    return fetch_project_summary("fabric-api", timeout=timeout)


def _parse_dependency_type(raw_dependency_type: str | None) -> DependencyType:
    if raw_dependency_type is None:
        raise ValueError("Modrinth dependency is missing 'dependency_type'.")

    try:
        return DependencyType(raw_dependency_type)
    except ValueError as exc:
        raise ValueError(f"Unknown Modrinth dependency_type '{raw_dependency_type}'.") from exc
