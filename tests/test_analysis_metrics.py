from __future__ import annotations

from modpack_solver.analysis import ExperimentCaseResult, ExperimentSystem, RuntimeMeasurements, build_grouped_metrics, summarize_experiment_results
from modpack_solver.evaluation.models import EvaluationSourceType


def test_repair_success_excludes_valid_controls_and_no_solution_cases() -> None:
    summary = summarize_experiment_results(
        [
            _result("valid", initially_compatible=True),
            _result("repair", repair_expected=True, solution_found=True, final_compatible=True),
            _result("no-solution", no_solution_expected=True),
        ]
    )

    assert summary.repairable_invalid_cases == 1
    assert summary.repair_success_rate == 1.0


def test_preservation_and_cost_use_repaired_invalid_cases() -> None:
    summary = summarize_experiment_results(
        [
            _result("valid", initially_compatible=True, preservation_rate=0.0, total_cost=99),
            _result("repair", repair_expected=True, solution_found=True, final_compatible=True, preservation_rate=0.5, total_cost=4),
        ]
    )

    assert summary.average_repair_preservation_rate == 0.5
    assert summary.average_repair_cost == 4.0


def test_synthetic_and_cached_real_grouping_work() -> None:
    groups = build_grouped_metrics(
        [
            _result("synthetic", source_type=EvaluationSourceType.SYNTHETIC),
            _result("real", source_type=EvaluationSourceType.CACHED_REAL),
        ]
    )

    by_name = {group.group_name: group for group in groups}
    assert by_name["Synthetic cases"].total_cases == 1
    assert by_name["Cached and modified real cases"].total_cases == 1


def test_single_and_multi_action_grouping_work() -> None:
    groups = build_grouped_metrics(
        [
            _result("single", repair_expected=True, action_count=1, solution_found=True, final_compatible=True),
            _result("multi", repair_expected=True, action_count=2, solution_found=True, final_compatible=True),
        ]
    )

    by_name = {group.group_name: group for group in groups}
    assert by_name["Single-action repairs"].total_cases == 1
    assert by_name["Multi-action repairs"].total_cases == 1


def test_empty_groups_produce_safe_values_without_nan_or_infinity() -> None:
    summary = summarize_experiment_results([])

    assert summary.repair_success_rate == 0.0
    assert summary.average_repair_cost is None
    assert summary.median_runtime_seconds == 0.0


def _result(
    case_id: str,
    *,
    source_type: EvaluationSourceType = EvaluationSourceType.SYNTHETIC,
    initially_compatible: bool = False,
    repair_expected: bool = False,
    no_solution_expected: bool = False,
    solution_found: bool = False,
    final_compatible: bool = False,
    preservation_rate: float = 1.0,
    total_cost: int | None = 0,
    action_count: int = 0,
) -> ExperimentCaseResult:
    return ExperimentCaseResult(
        case_id=case_id,
        name=case_id,
        source_type=source_type,
        system=ExperimentSystem.WEIGHTED_DEFAULT,
        profile_id="default",
        initially_compatible=initially_compatible,
        repair_expected=repair_expected,
        no_solution_expected=no_solution_expected,
        solution_found=solution_found,
        final_compatible=final_compatible,
        total_cost=total_cost,
        action_count=action_count,
        preservation_rate=preservation_rate,
        runtime=RuntimeMeasurements(samples_seconds=[0.0], median_seconds=0.0),
        issue_detection_correct=True,
    )
