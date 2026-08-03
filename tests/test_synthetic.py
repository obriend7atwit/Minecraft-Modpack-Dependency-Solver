from __future__ import annotations

from pathlib import Path

import pytest

from modpack_solver.metadata.synthetic import load_synthetic_case, load_synthetic_cases


FIXTURE_DIR = Path("data/synthetic")
FIXTURE_NAMES = [
    "valid_modpack.json",
    "missing_required_dependency.json",
    "minecraft_version_mismatch.json",
    "loader_mismatch.json",
    "hard_conflict.json",
    "optional_dependency_warning.json",
    "embedded_dependency.json",
    "multi_repair.json",
    "version_choice.json",
    "no_solution.json",
    "tie_breaking.json",
    "dependency_chain_missing.json",
    "dependency_chain_valid.json",
    "combined_missing_and_conflict.json",
    "multiple_missing_dependencies.json",
    "duplicate_selected_versions.json",
    "unresolved_selected_mod.json",
    "optional_and_embedded.json",
]


def test_valid_modpack_fixture_loads_successfully() -> None:
    case = load_synthetic_case(FIXTURE_DIR / "valid_modpack.json")

    assert case.config.minecraft_version == "1.20.1"
    assert case.config.loader == "fabric"
    assert len(case.projects) == 2
    assert len(case.versions) == 2


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_all_synthetic_fixtures_load_successfully(fixture_name: str) -> None:
    case = load_synthetic_case(FIXTURE_DIR / fixture_name)

    assert case.config.selected_mods
    assert case.projects
    assert case.versions


def test_load_synthetic_cases_loads_all_json_fixtures() -> None:
    cases = load_synthetic_cases(FIXTURE_DIR)

    assert len(cases) == len(FIXTURE_NAMES)
