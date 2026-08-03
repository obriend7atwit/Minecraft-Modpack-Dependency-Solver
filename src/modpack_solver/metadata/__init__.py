"""Metadata parsing and ingestion helpers."""

from modpack_solver.metadata.cache import cache_raw_response, load_json, save_json
from modpack_solver.metadata.modrinth import (
    check_modrinth_fabric_api_access,
    fetch_project_summary,
    fetch_project_versions,
    get_normalized_project_versions,
    normalize_modrinth_dependency,
    normalize_modrinth_version,
)
from modpack_solver.metadata.synthetic import load_synthetic_case, load_synthetic_cases

__all__ = [
    "cache_raw_response",
    "check_modrinth_fabric_api_access",
    "fetch_project_summary",
    "fetch_project_versions",
    "get_normalized_project_versions",
    "load_json",
    "load_synthetic_case",
    "load_synthetic_cases",
    "normalize_modrinth_dependency",
    "normalize_modrinth_version",
    "save_json",
]
