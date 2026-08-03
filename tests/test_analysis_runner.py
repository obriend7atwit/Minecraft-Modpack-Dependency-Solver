from __future__ import annotations

import uuid
from pathlib import Path

import modpack_solver.metadata.modrinth as modrinth
from modpack_solver.analysis import (
    get_default_profile,
    get_preservation_profile,
    run_baseline_experiment,
    run_profile_experiment,
    run_week9_analysis,
)
from modpack_solver.evaluation import run_evaluation


MANIFEST = Path("data/evaluation/manifest.json")


def test_strict_validation_runs_first_and_week8_evaluator_remains_unchanged() -> None:
    result = run_week9_analysis(
        output_dir=_workspace_dir(),
        runtime_repetitions=1,
        skip_charts=True,
        case_ids={"synthetic-valid"},
    )

    assert result.strict_validation_passed is True
    assert run_evaluation(MANIFEST, case_ids={"synthetic-valid"}).summary.failed_cases == 0


def test_default_and_preservation_profile_experiments_work() -> None:
    default_results, default_summary = run_profile_experiment(
        MANIFEST,
        get_default_profile(),
        runtime_repetitions=1,
        case_ids={"synthetic-missing-dependency"},
    )
    preservation_results, preservation_summary = run_profile_experiment(
        MANIFEST,
        get_preservation_profile(),
        runtime_repetitions=1,
        case_ids={"synthetic-missing-dependency"},
    )

    assert default_results[0].final_compatible is True
    assert preservation_results[0].final_compatible is True
    assert default_summary.grouped_metrics
    assert preservation_summary.grouped_metrics


def test_baseline_experiment_works() -> None:
    results, summary = run_baseline_experiment(
        MANIFEST,
        runtime_repetitions=1,
        case_ids={"synthetic-missing-dependency"},
    )

    assert results[0].final_compatible is True
    assert summary.validated_baseline_repair_rate == 1.0


def test_case_filtering_runtime_configuration_and_generated_files() -> None:
    result = run_week9_analysis(
        output_dir=_workspace_dir(),
        runtime_repetitions=1,
        skip_charts=True,
        case_ids={"synthetic-valid", "controlled-preservation-tradeoff"},
    )

    assert result.runtime_repetitions == 1
    assert result.generated_files
    assert all("real-" not in case.case_id for case in result.case_results)


def test_controlled_tradeoff_and_search_limit_results_are_included() -> None:
    result = run_week9_analysis(
        output_dir=_workspace_dir(),
        runtime_repetitions=1,
        skip_charts=True,
        case_ids={"synthetic-missing-dependency", "controlled-preservation-tradeoff"},
    )

    assert "controlled-preservation-tradeoff" in result.changed_decision_cases
    assert result.search_limit_results


def test_complete_limited_analysis_runs_offline(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("Live Modrinth access should not be used.")

    monkeypatch.setattr(modrinth, "fetch_project_summary", fail)
    monkeypatch.setattr(modrinth, "fetch_project_versions", fail)
    monkeypatch.setattr(modrinth, "get_normalized_project_versions", fail)

    result = run_week9_analysis(
        output_dir=_workspace_dir(),
        runtime_repetitions=1,
        skip_charts=True,
        case_ids={"synthetic-valid", "real-additive-missing-dependency"},
    )

    assert result.strict_validation_passed is True


def _workspace_dir() -> Path:
    path = Path(".test-artifacts") / "analysis-runner" / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path
