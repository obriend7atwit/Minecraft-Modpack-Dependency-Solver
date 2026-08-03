"""Pure metric calculations for offline evaluation runs."""

from __future__ import annotations

from modpack_solver.evaluation.models import EvaluationCaseResult, EvaluationSummary
from modpack_solver.solver.checker import CompatibilityStatus
from modpack_solver.solver.common import SolverStatus


def preservation_rate(original_mod_count: int, preserved_mod_count: int) -> float:
    """Return preserved/original, using 1.0 when no original mods were selected."""

    if original_mod_count <= 0:
        return 1.0
    return preserved_mod_count / original_mod_count


def repair_success_rate(results: list[EvaluationCaseResult]) -> float:
    """Return success rate across invalid cases expected to be repairable."""

    repairable = [
        result
        for result in results
        if result.expected_initial_status == CompatibilityStatus.INCOMPATIBLE
        and result.expected_solver_status == SolverStatus.SOLUTION_FOUND
    ]
    if not repairable:
        return 0.0
    repaired = [
        result
        for result in repairable
        if result.solver_status == SolverStatus.SOLUTION_FOUND and result.final_compatible
    ]
    return len(repaired) / len(repairable)


def issue_detection_recall(results: list[EvaluationCaseResult]) -> float:
    """Return recall across all expected issue types."""

    expected_count = 0
    matched_count = 0
    for result in results:
        expected_count += len(result.expected_issue_types)
        matched_count += sum(issue_type in result.initial_issue_types for issue_type in result.expected_issue_types)
    if expected_count == 0:
        return 0.0
    return matched_count / expected_count


def summarize_results(results: list[EvaluationCaseResult]) -> EvaluationSummary:
    """Summarize evaluation results without rerunning checker or solver logic."""

    total_cases = len(results)
    passed_cases = sum(result.passed for result in results)
    failed_cases = total_cases - passed_cases
    repairable_invalid_cases = sum(
        result.expected_initial_status == CompatibilityStatus.INCOMPATIBLE
        and result.expected_solver_status == SolverStatus.SOLUTION_FOUND
        for result in results
    )
    successfully_repaired_cases = sum(
        result.expected_initial_status == CompatibilityStatus.INCOMPATIBLE
        and result.expected_solver_status == SolverStatus.SOLUTION_FOUND
        and result.solver_status == SolverStatus.SOLUTION_FOUND
        and result.final_compatible
        for result in results
    )
    exact_issue_match_cases = sum(result.exact_issue_match for result in results)
    cost_values = [result.total_cost for result in results if result.total_cost is not None]

    return EvaluationSummary(
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        case_pass_rate=passed_cases / total_cases if total_cases else 0.0,
        repairable_invalid_cases=repairable_invalid_cases,
        successfully_repaired_cases=successfully_repaired_cases,
        repair_success_rate=repair_success_rate(results),
        average_preservation_rate=_mean([result.preservation_rate for result in results]),
        average_weighted_cost=_mean(cost_values) if cost_values else None,
        average_action_count=_mean([result.action_count for result in results]),
        average_removed_mods=_mean([result.removed_mod_count for result in results]),
        average_runtime_seconds=_mean([result.runtime_seconds for result in results]),
        average_states_expanded=_mean([result.states_expanded for result in results]),
        exact_issue_match_cases=exact_issue_match_cases,
        issue_detection_case_accuracy=exact_issue_match_cases / total_cases if total_cases else 0.0,
        issue_detection_recall=issue_detection_recall(results),
    )


def _mean(values: list[float | int]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / len(values)
