from __future__ import annotations

from pathlib import Path

from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.models import (
    Dependency,
    DependencyType,
    MetadataSource,
    ModProject,
    ModVersion,
    ModpackConfig,
    SelectedMod,
    SyntheticCase,
)
from modpack_solver.solver.checker import CompatibilityStatus, check_graph, check_synthetic_case


FIXTURE_DIR = Path("data/synthetic")


def _load_case(name: str) -> SyntheticCase:
    return load_synthetic_case(FIXTURE_DIR / name)


def test_valid_modpack_reports_compatible() -> None:
    report = check_synthetic_case(_load_case("valid_modpack.json"))

    assert report.status == CompatibilityStatus.COMPATIBLE
    assert not any(issue.severity == "error" for issue in report.issues)


def test_missing_required_dependency_reports_incompatible() -> None:
    report = check_synthetic_case(_load_case("missing_required_dependency.json"))

    assert report.status == CompatibilityStatus.INCOMPATIBLE
    assert any(issue.issue_type.value == "missing_dependency" for issue in report.issues)


def test_minecraft_version_mismatch_reports_incompatible() -> None:
    report = check_synthetic_case(_load_case("minecraft_version_mismatch.json"))

    assert report.status == CompatibilityStatus.INCOMPATIBLE
    assert any(issue.issue_type.value == "minecraft_version_mismatch" for issue in report.issues)


def test_loader_mismatch_reports_incompatible() -> None:
    report = check_synthetic_case(_load_case("loader_mismatch.json"))

    assert report.status == CompatibilityStatus.INCOMPATIBLE
    assert any(issue.issue_type.value == "loader_mismatch" for issue in report.issues)


def test_hard_conflict_reports_incompatible() -> None:
    report = check_synthetic_case(_load_case("hard_conflict.json"))

    assert report.status == CompatibilityStatus.INCOMPATIBLE
    assert any(issue.issue_type.value == "hard_conflict" for issue in report.issues)


def test_optional_dependency_reports_compatible_with_warnings() -> None:
    report = check_synthetic_case(_load_case("optional_dependency_warning.json"))

    assert report.status == CompatibilityStatus.COMPATIBLE_WITH_WARNINGS
    assert any(issue.issue_type.value == "optional_dependency_warning" for issue in report.issues)


def test_embedded_dependency_does_not_report_missing_required_dependency() -> None:
    report = check_synthetic_case(_load_case("embedded_dependency.json"))

    assert not any(issue.issue_type.value == "missing_dependency" for issue in report.issues)
    assert any(issue.issue_type.value == "embedded_dependency_info" for issue in report.issues)


def test_duplicate_selected_version_reports_incompatible() -> None:
    case = SyntheticCase(
        config=ModpackConfig(
            minecraft_version="1.20.1",
            loader="fabric",
            selected_mods=[
                SelectedMod(mod_id="example-library", version_id="example-library-1.0.0"),
                SelectedMod(mod_id="example-library", version_id="example-library-1.0.0"),
            ],
        ),
        projects=[
            ModProject(
                mod_id="example-library",
                name="Example Library",
                slug="example-library",
                source=MetadataSource.SYNTHETIC,
            )
        ],
        versions=[
            ModVersion(
                version_id="example-library-1.0.0",
                mod_id="example-library",
                version_number="1.0.0",
                game_versions=["1.20.1"],
                loaders=["fabric"],
            )
        ],
    )

    report = check_synthetic_case(case)

    assert report.status == CompatibilityStatus.INCOMPATIBLE
    assert any(issue.issue_type.value == "duplicate_mod_version" for issue in report.issues)


def test_unresolved_selected_mod_reports_incompatible() -> None:
    case = SyntheticCase(
        config=ModpackConfig(
            minecraft_version="1.20.1",
            loader="fabric",
            selected_mods=[SelectedMod(mod_id="missing-mod", version_id="missing-mod-1.0.0")],
        ),
        projects=[],
        versions=[],
    )

    report = check_synthetic_case(case)

    assert report.status == CompatibilityStatus.INCOMPATIBLE
    assert any(issue.issue_type.value == "unresolved_selected_mod" for issue in report.issues)


def test_unknown_required_dependency_target_produces_error() -> None:
    case = SyntheticCase(
        config=ModpackConfig(
            minecraft_version="1.20.1",
            loader="fabric",
            selected_mods=[SelectedMod(mod_id="example-machines", version_id="example-machines-1.0.0")],
        ),
        projects=[
            ModProject(
                mod_id="example-machines",
                name="Example Machines",
                slug="example-machines",
                source=MetadataSource.SYNTHETIC,
            )
        ],
        versions=[
            ModVersion(
                version_id="example-machines-1.0.0",
                mod_id="example-machines",
                version_number="1.0.0",
                game_versions=["1.20.1"],
                loaders=["fabric"],
                dependencies=[
                    Dependency(
                        target_mod_id="unknown-library",
                        dependency_type=DependencyType.REQUIRED,
                        source=MetadataSource.SYNTHETIC,
                    )
                ],
            )
        ],
    )

    report = check_graph(build_graph_from_synthetic_case(case))

    assert report.status == CompatibilityStatus.INCOMPATIBLE
    assert any(issue.issue_type.value == "unknown_dependency_target" for issue in report.issues)
