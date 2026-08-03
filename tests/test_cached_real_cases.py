from __future__ import annotations

from pathlib import Path

from modpack_solver.evaluation import EvaluationSourceType, load_evaluation_manifest
from modpack_solver.metadata.synthetic import load_synthetic_case
import modpack_solver.metadata.modrinth as modrinth
from modpack_solver.solver import check_synthetic_case


CACHED_REAL_DIR = Path("data/evaluation/cached_real")
MANIFEST_PATH = Path("data/evaluation/manifest.json")


def _cached_case(name: str):
    return load_synthetic_case(CACHED_REAL_DIR / name)


def test_all_cached_real_fixture_files_load_offline() -> None:
    for path in sorted(CACHED_REAL_DIR.glob("*.json")):
        case = load_synthetic_case(path)
        assert case.projects
        assert case.versions


def test_valid_reduced_sample_passes_checking() -> None:
    report = check_synthetic_case(_cached_case("fabulously_optimized_valid.json"))

    assert report.status.value == "compatible"


def test_intentionally_broken_sample_reports_expected_issue() -> None:
    report = check_synthetic_case(_cached_case("additive_missing_dependency.json"))

    assert report.status.value == "incompatible"
    assert any(issue.issue_type.value == "missing_dependency" for issue in report.issues)


def test_source_notes_clearly_label_modified_cases() -> None:
    specs = load_evaluation_manifest(MANIFEST_PATH)
    modified_specs = [spec for spec in specs if spec.source_type == EvaluationSourceType.MODIFIED_REAL]

    assert modified_specs
    assert all("modified" in (spec.notes or "").lower() or "intentionally" in (spec.notes or "").lower() for spec in modified_specs)


def test_cached_real_cases_do_not_call_live_modrinth(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("Live Modrinth access should not be called for cached real cases.")

    monkeypatch.setattr(modrinth, "fetch_project_summary", fail)
    monkeypatch.setattr(modrinth, "fetch_project_versions", fail)
    monkeypatch.setattr(modrinth, "get_normalized_project_versions", fail)

    check_synthetic_case(_cached_case("fabulously_optimized_valid.json"))
    check_synthetic_case(_cached_case("additive_missing_dependency.json"))
