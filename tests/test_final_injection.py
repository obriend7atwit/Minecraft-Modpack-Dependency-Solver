from modpack_solver.final_dataset.injection import (
    inject_add_conflicting_mod,
    inject_duplicate_mod_version,
    inject_incompatible_version,
    inject_loader_mismatch,
    inject_minecraft_version_mismatch,
    inject_multi_error,
    inject_remove_dependency_metadata,
    inject_remove_required_dependency,
    write_injection_log,
)
from modpack_solver.final_dataset.models import ModificationType
from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.models import IssueType
from modpack_solver.models import Dependency, DependencyType, MetadataSource, ModProject, ModVersion
from modpack_solver.solver.checker import check_graph


def test_remove_dependency_does_not_mutate_original():
    case = load_synthetic_case("data/synthetic/valid_modpack.json")
    original_selected = [selected.mod_id for selected in case.config.selected_mods]
    result = inject_remove_required_dependency(case)
    assert [selected.mod_id for selected in case.config.selected_mods] == original_selected
    assert "example-library" not in {selected.mod_id for selected in result.modified_case.config.selected_mods}
    assert IssueType.MISSING_DEPENDENCY in result.expected_issue_types


def test_minecraft_and_loader_mismatch_injections_work():
    case = load_synthetic_case("data/synthetic/valid_modpack.json")
    minecraft = inject_minecraft_version_mismatch(case, new_minecraft_version="1.19.4")
    loader = inject_loader_mismatch(case, new_loader="forge")
    assert IssueType.MINECRAFT_VERSION_MISMATCH in minecraft.expected_issue_types
    assert IssueType.LOADER_MISMATCH in loader.expected_issue_types


def test_incompatible_version_injection_uses_available_alternative():
    case = load_synthetic_case("data/synthetic/valid_modpack.json")
    original = case.versions[0]
    case.versions.append(
        original.model_copy(
            update={
                "version_id": "machines-incompatible",
                "version_number": "0.5.0",
                "game_versions": ["1.19.4"],
            },
            deep=True,
        )
    )
    result = inject_incompatible_version(case, target_mod_id="example-machines")
    assert result.modification_type == ModificationType.REPLACE_WITH_INCOMPATIBLE_VERSION
    assert IssueType.MINECRAFT_VERSION_MISMATCH in result.expected_issue_types


def test_duplicate_and_metadata_removal_injections_work():
    case = load_synthetic_case("data/synthetic/valid_modpack.json")
    duplicate = inject_duplicate_mod_version(case, target_mod_id="example-machines")
    metadata = inject_remove_dependency_metadata(case, target_mod_id="example-library")
    assert IssueType.DUPLICATE_MOD_VERSION in duplicate.expected_issue_types
    observed = {issue.issue_type for issue in check_graph(build_graph_from_synthetic_case(metadata.modified_case)).issues}
    assert IssueType.UNKNOWN_DEPENDENCY_TARGET in observed


def test_add_conflicting_mod_injection_uses_available_metadata():
    case = load_synthetic_case("data/synthetic/valid_modpack.json")
    conflict_id = "example-conflict"
    case.projects.append(
        ModProject(
            mod_id=conflict_id,
            name="Example Conflict",
            slug=conflict_id,
            source=MetadataSource.SYNTHETIC,
        )
    )
    case.versions.append(
        ModVersion(
            version_id="example-conflict-1.0.0",
            mod_id=conflict_id,
            version_number="1.0.0",
            game_versions=["1.20.1"],
            loaders=["fabric"],
        )
    )
    case.versions[0].dependencies.append(
        Dependency(target_mod_id=conflict_id, dependency_type=DependencyType.INCOMPATIBLE)
    )
    result = inject_add_conflicting_mod(case, target_mod_id=conflict_id)
    assert IssueType.HARD_CONFLICT in result.expected_issue_types
    assert conflict_id in {selected.mod_id for selected in result.modified_case.config.selected_mods}


def test_multi_error_records_each_applied_change_and_writes_log(tmp_path):
    case = load_synthetic_case("data/synthetic/valid_modpack.json")
    result = inject_multi_error(
        case,
        [ModificationType.REMOVE_REQUIRED_DEPENDENCY, ModificationType.CHANGE_LOADER],
    )
    assert result.modification_type == ModificationType.MULTI_ERROR
    assert result.applied_modifications == [
        ModificationType.REMOVE_REQUIRED_DEPENDENCY,
        ModificationType.CHANGE_LOADER,
    ]
    path = write_injection_log(result, tmp_path / "logs" / "injection.json")
    assert path.exists()
    assert "modified_case" not in path.read_text(encoding="utf-8")
