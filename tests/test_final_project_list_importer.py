import pytest

from modpack_solver.final_dataset.cache import save_cached_json
from modpack_solver.importers.project_list_importer import (
    build_case_from_project_list,
    parse_project_list,
)


def test_parse_newline_and_comma_project_lists():
    assert parse_project_list("sodium\nfabric-api,modmenu") == ["sodium", "fabric-api", "modmenu"]


def test_parse_project_list_removes_duplicates_stably():
    assert parse_project_list("Sodium,sodium,fabric-api,SODIUM") == ["Sodium", "fabric-api"]


def test_parse_project_list_rejects_empty_text():
    with pytest.raises(ValueError, match="empty"):
        parse_project_list(" , \n")


def test_build_case_uses_offline_cache_and_includes_dependency_metadata(tmp_path):
    project = {"id": "main-id", "slug": "main", "title": "Main"}
    helper = {"id": "helper-id", "slug": "helper", "title": "Helper"}
    main_versions = [
        {
            "id": "main-v1",
            "project_id": "main-id",
            "version_number": "1.0.0",
            "game_versions": ["1.20.1"],
            "loaders": ["fabric"],
            "dependencies": [{"project_id": "helper-id", "dependency_type": "required"}],
        }
    ]
    helper_versions = [
        {
            "id": "helper-v1",
            "project_id": "helper-id",
            "version_number": "1.0.0",
            "game_versions": ["1.20.1"],
            "loaders": ["fabric"],
            "dependencies": [],
        }
    ]
    for category, key, value in (
        ("projects", "main", project),
        ("versions", "main", main_versions),
        ("projects", "helper-id", helper),
        ("versions", "helper-id", helper_versions),
    ):
        save_cached_json(tmp_path / "raw" / category / f"{key}.json", value)

    case = build_case_from_project_list(
        ["main"], "1.20.1", "fabric", cache_dir=tmp_path, allow_live=False
    )
    assert [selected.mod_id for selected in case.config.selected_mods] == ["main-id"]
    assert {project.mod_id for project in case.projects} == {"main-id", "helper-id"}
    assert {version.version_id for version in case.versions} == {"main-v1", "helper-v1"}


def test_build_case_never_uses_network_in_offline_mode(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_case_from_project_list(
            ["missing"], "1.20.1", "fabric", cache_dir=tmp_path, allow_live=False
        )
