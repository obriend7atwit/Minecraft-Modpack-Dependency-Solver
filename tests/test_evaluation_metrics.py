from __future__ import annotations

from modpack_solver.evaluation import issue_detection_recall, preservation_rate, repair_success_rate, summarize_results
from modpack_solver.evaluation.models import EvaluationCaseResult, EvaluationSourceType
from modpack_solver.models import IssueType, RepairActionType
from modpack_solver.solver import CompatibilityStatus, SolverStatus


def test_preservation_rate_uses_full_score_for_zero_original_mods() -> None:
    assert preservation_rate(0, 0) == 1.0


def test_repair_success_rate_uses_only_repairable_invalid_cases() -> None:
    results = [
        _make_result(
            case_id="repair-pass",
            expected_initial_status=CompatibilityStatus.INCOMPATIBLE,
            expected_solver_status=SolverStatus.SOLUTION_FOUND,
            initial_status=CompatibilityStatus.INCOMPATIBLE,
            solver_status=SolverStatus.SOLUTION_FOUND,
            final_compatible=True,
            passed=True,
        ),
        _make_result(
            case_id="repair-fail",
            expected_initial_status=CompatibilityStatus.INCOMPATIBLE,
            expected_solver_status=SolverStatus.SOLUTION_FOUND,
            initial_status=CompatibilityStatus.INCOMPATIBLE,
            solver_status=SolverStatus.NO_SOLUTION,
            final_compatible=False,
            passed=False,
        ),
        _make_result(case_id="valid-control"),
    ]

    assert repair_success_rate(results) == 0.5


def test_issue_detection_recall_matches_expected_issue_counts() -> None:
    results = [
        _make_result(
            case_id="recall-a",
            expected_issue_types=[IssueType.MISSING_DEPENDENCY, IssueType.HARD_CONFLICT],
            initial_issue_types=[IssueType.MISSING_DEPENDENCY],
        ),
        _make_result(
            case_id="recall-b",
            expected_issue_types=[IssueType.LOADER_MISMATCH],
            initial_issue_types=[IssueType.LOADER_MISMATCH],
        ),
    ]

    assert issue_detection_recall(results) == 2 / 3


def test_summarize_results_computes_averages_and_accuracy() -> None:
    results = [
        _make_result(
            case_id="a",
            expected_initial_status=CompatibilityStatus.INCOMPATIBLE,
            expected_solver_status=SolverStatus.SOLUTION_FOUND,
            initial_status=CompatibilityStatus.INCOMPATIBLE,
            solver_status=SolverStatus.SOLUTION_FOUND,
            expected_issue_types=[IssueType.MISSING_DEPENDENCY],
            initial_issue_types=[IssueType.MISSING_DEPENDENCY],
            action_types=[RepairActionType.ADD_DEPENDENCY],
            final_compatible=True,
            total_cost=1,
            action_count=1,
            preservation_rate=1.0,
            removed_mod_count=0,
            runtime_seconds=0.1,
            states_expanded=2,
            exact_issue_match=True,
            passed=True,
        ),
        _make_result(
            case_id="b",
            expected_initial_status=CompatibilityStatus.INCOMPATIBLE,
            expected_solver_status=SolverStatus.NO_SOLUTION,
            initial_status=CompatibilityStatus.INCOMPATIBLE,
            solver_status=SolverStatus.NO_SOLUTION,
            expected_issue_types=[IssueType.LOADER_MISMATCH],
            initial_issue_types=[IssueType.LOADER_MISMATCH],
            final_compatible=False,
            total_cost=None,
            action_count=0,
            preservation_rate=0.5,
            removed_mod_count=1,
            runtime_seconds=0.3,
            states_expanded=5,
            exact_issue_match=True,
            passed=True,
        ),
    ]

    summary = summarize_results(results)

    assert summary.total_cases == 2
    assert summary.passed_cases == 2
    assert summary.failed_cases == 0
    assert summary.case_pass_rate == 1.0
    assert summary.repair_success_rate == 1.0
    assert summary.average_preservation_rate == 0.75
    assert summary.average_weighted_cost == 1.0
    assert summary.average_action_count == 0.5
    assert summary.average_removed_mods == 0.5
    assert summary.average_runtime_seconds == 0.2
    assert summary.average_states_expanded == 3.5
    assert summary.issue_detection_case_accuracy == 1.0
    assert summary.issue_detection_recall == 1.0


def test_empty_denominators_are_safe() -> None:
    summary = summarize_results([])

    assert summary.total_cases == 0
    assert summary.case_pass_rate == 0.0
    assert summary.repair_success_rate == 0.0
    assert summary.average_weighted_cost is None
    assert summary.issue_detection_recall == 0.0


def _make_result(
    *,
    case_id: str,
    expected_initial_status: CompatibilityStatus = CompatibilityStatus.COMPATIBLE,
    expected_solver_status: SolverStatus = SolverStatus.ALREADY_COMPATIBLE,
    expected_issue_types: list[IssueType] | None = None,
    initial_status: CompatibilityStatus = CompatibilityStatus.COMPATIBLE,
    solver_status: SolverStatus = SolverStatus.ALREADY_COMPATIBLE,
    initial_issue_types: list[IssueType] | None = None,
    action_types: list[RepairActionType] | None = None,
    final_compatible: bool = True,
    total_cost: int | None = 0,
    action_count: int = 0,
    preservation_rate: float = 1.0,
    removed_mod_count: int = 0,
    runtime_seconds: float = 0.0,
    states_expanded: int = 0,
    exact_issue_match: bool = False,
    passed: bool = True,
) -> EvaluationCaseResult:
    return EvaluationCaseResult(
        case_id=case_id,
        name=case_id,
        source_type=EvaluationSourceType.SYNTHETIC,
        expected_initial_status=expected_initial_status,
        expected_solver_status=expected_solver_status,
        expected_issue_types=expected_issue_types or [],
        initial_status=initial_status,
        solver_status=solver_status,
        initial_issue_types=initial_issue_types or [],
        action_types=action_types or [],
        final_compatible=final_compatible,
        total_cost=total_cost,
        action_count=action_count,
        original_mods_preserved=1,
        original_mod_count=1,
        preservation_rate=preservation_rate,
        removed_mod_count=removed_mod_count,
        runtime_seconds=runtime_seconds,
        states_expanded=states_expanded,
        status_passed=passed,
        issues_passed=passed,
        actions_passed=passed,
        cost_passed=passed,
        preservation_passed=passed,
        final_compatibility_passed=passed,
        exact_issue_match=exact_issue_match,
        passed=passed,
        explanation_root_cause_present=True,
        explanation_affected_mods_present=True,
        explanation_repair_present=True,
        explanation_chain_present_when_expected=True,
        failure_reasons=[] if passed else ["failed"],
    )
