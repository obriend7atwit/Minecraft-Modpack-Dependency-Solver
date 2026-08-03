"""Supported final-system input adapters."""

from modpack_solver.importers.json_importer import load_case_json
from modpack_solver.importers.modrinth_url import (
    ModrinthResourceKind,
    ParsedModrinthUrl,
    parse_modrinth_url,
)
from modpack_solver.importers.mrpack_importer import (
    ImportedModpack,
    ImportedModpackFile,
    extract_modrinth_ids_from_downloads,
    read_mrpack,
)
from modpack_solver.importers.project_list_importer import (
    build_case_from_project_list,
    parse_project_list,
)

__all__ = [
    "ImportedModpack",
    "ImportedModpackFile",
    "ModrinthResourceKind",
    "ParsedModrinthUrl",
    "build_case_from_project_list",
    "extract_modrinth_ids_from_downloads",
    "load_case_json",
    "parse_modrinth_url",
    "parse_project_list",
    "read_mrpack",
]
