"""Project-list parsing and Modrinth-backed case construction."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from modpack_solver.final_dataset.cache import (
    ModrinthCacheMode,
    fetch_or_load_project,
    fetch_or_load_project_versions,
)
from modpack_solver.metadata.modrinth import normalize_modrinth_version
from modpack_solver.models import MetadataSource, ModProject, ModpackConfig, SelectedMod, SyntheticCase
from modpack_solver.versioning import version_sort_key


def parse_project_list(text: str) -> list[str]:
    """Parse comma/newline-separated IDs or slugs with stable de-duplication."""

    values = [value.strip() for value in re.split(r"[\r\n,]+", text) if value.strip()]
    if not values:
        raise ValueError("Project list cannot be empty.")
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    return ordered


def build_case_from_project_list(
    project_slugs: Sequence[str],
    minecraft_version: str,
    loader: str,
    *,
    cache_dir: str | Path,
    allow_live: bool,
) -> SyntheticCase:
    """Resolve selected projects and known dependencies using cache-first metadata."""

    ordered_slugs = parse_project_list("\n".join(project_slugs))
    if not minecraft_version.strip() or not loader.strip():
        raise ValueError("Minecraft version and loader are required for project-list import.")
    mode = ModrinthCacheMode.LIVE if allow_live else ModrinthCacheMode.OFFLINE

    projects_by_id: dict[str, ModProject] = {}
    versions_by_id = {}
    selected_mods: list[SelectedMod] = []
    dependency_targets: list[str] = []

    for slug in ordered_slugs:
        project, versions = _load_project_bundle(slug, cache_dir=cache_dir, mode=mode)
        projects_by_id[project.mod_id] = project
        for version in versions:
            versions_by_id[version.version_id] = version
        selected_version = _select_compatible_version(versions, minecraft_version, loader)
        if selected_version is None:
            raise ValueError(
                f"Project '{slug}' has no cached version compatible with Minecraft "
                f"{minecraft_version} and loader {loader}."
            )
        selected_mods.append(
            SelectedMod(
                mod_id=selected_version.mod_id,
                version_id=selected_version.version_id,
                version_number=selected_version.version_number,
            )
        )
        dependency_targets.extend(
            dependency.target_mod_id
            for dependency in selected_version.dependencies
            if dependency.target_mod_id != "unknown"
        )

    # Dependency metadata is useful to the solver even when the dependency is not selected.
    for target in _stable_unique(dependency_targets):
        if target in projects_by_id:
            continue
        try:
            project, versions = _load_project_bundle(target, cache_dir=cache_dir, mode=mode)
        except (FileNotFoundError, ValueError):
            continue
        projects_by_id[project.mod_id] = project
        for version in versions:
            versions_by_id[version.version_id] = version

    return SyntheticCase(
        config=ModpackConfig(
            minecraft_version=minecraft_version.strip(),
            loader=loader.strip().lower(),
            selected_mods=selected_mods,
        ),
        projects=sorted(projects_by_id.values(), key=lambda project: project.mod_id),
        versions=sorted(versions_by_id.values(), key=lambda version: (version.mod_id, version.version_id)),
    )


def _load_project_bundle(project_id_or_slug: str, *, cache_dir: str | Path, mode: ModrinthCacheMode):
    raw_project = fetch_or_load_project(project_id_or_slug, cache_dir=cache_dir, mode=mode)
    raw_versions = fetch_or_load_project_versions(project_id_or_slug, cache_dir=cache_dir, mode=mode)
    project_id = str(raw_project.get("id") or project_id_or_slug)
    project = ModProject(
        mod_id=project_id,
        name=str(raw_project.get("title") or raw_project.get("name") or raw_project.get("slug") or project_id),
        slug=raw_project.get("slug"),
        source=MetadataSource.MODRINTH,
        author=raw_project.get("author"),
        description=raw_project.get("description"),
    )
    versions = []
    for raw_version in raw_versions:
        normalized_raw = dict(raw_version)
        normalized_raw.setdefault("project_id", project_id)
        versions.append(normalize_modrinth_version(normalized_raw))
    return project, versions


def _select_compatible_version(versions, minecraft_version: str, loader: str):
    compatible = [
        version
        for version in versions
        if minecraft_version in version.game_versions and loader.lower() in {item.lower() for item in version.loaders}
    ]
    if not compatible:
        return None
    return max(
        compatible,
        key=lambda version: (version_sort_key(version.version_number), version.version_id),
    )


def _stable_unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
