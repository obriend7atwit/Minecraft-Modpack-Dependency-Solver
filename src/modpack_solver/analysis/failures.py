"""Failure classification for Week 9 experimental results."""

from __future__ import annotations

from enum import Enum

from modpack_solver.analysis.models import ExperimentCaseResult, ExperimentSystem
from modpack_solver.evaluation.models import EvaluationCaseSpec
from modpack_solver.models import IssueType
from modpack_solver.solver import ExplanationReport, SolverResult, SolverStatus


class FailureCategory(str, Enum):
    INCORRECT_ISSUE_DETECTION = "incorrect_issue_detection"
    REPAIR_NOT_FOUND = "repair_not_found"
    INVALID_REPAIR = "invalid_repair"
    HIGHER_COST_REPAIR = "higher_cost_repair"
    EXCESSIVE_REMOVALS = "excessive_removals"
    SEARCH_LIMIT_REACHED = "search_limit_reached"
    TIMEOUT = "timeout"
    MISSING_METADATA = "missing_metadata"
    UNSUPPORTED_VERSION_FORMAT = "unsupported_version_format"
    INCOMPLETE_EXPLANATION = "incomplete_explanation"
    INCORRECT_EXPECTED_RESULT = "incorrect_expected_result"
    NON_EXECUTABLE_BASELINE = "non_executable_baseline"
    OTHER = "other"


def classify_failure(
    spec: EvaluationCaseSpec,
    result: ExperimentCaseResult,
    *,
    solver_result: SolverResult | None = None,
    explanation_report: ExplanationReport | None = None,
) -> FailureCategory | None:
    """Classify a failed or incomplete experimental outcome."""

    if result.status_correct and result.issue_detection_correct and result.repair_outcome_correct:
        return None

    if spec.expected_solver_status in {SolverStatus.NO_SOLUTION, SolverStatus.LIMIT_REACHED}:
        if result.issue_detection_correct and result.repair_outcome_correct:
            return None

    if not result.issue_detection_correct:
        return FailureCategory.INCORRECT_ISSUE_DETECTION

    if result.system == ExperimentSystem.BASELINE and result.suggestion_count and result.executable_suggestion_count == 0:
        return FailureCategory.NON_EXECUTABLE_BASELINE

    if solver_result is not None:
        if solver_result.status == SolverStatus.LIMIT_REACHED:
            return FailureCategory.SEARCH_LIMIT_REACHED
        if solver_result.status == SolverStatus.TIMEOUT:
            return FailureCategory.TIMEOUT

    if any(
        issue_type in result.issue_types
        for issue_type in {
            IssueType.UNKNOWN_DEPENDENCY_TARGET,
            IssueType.UNRESOLVED_SELECTED_MOD,
        }
    ):
        return FailureCategory.MISSING_METADATA

    if result.failure_detail and "higher cost" in result.failure_detail.lower():
        return FailureCategory.HIGHER_COST_REPAIR

    if result.failure_detail and "unsupported version" in result.failure_detail.lower():
        return FailureCategory.UNSUPPORTED_VERSION_FORMAT

    if explanation_report is not None and result.issue_types and not explanation_report.issue_explanations:
        return FailureCategory.INCOMPLETE_EXPLANATION

    if result.repair_expected and not result.solution_found:
        return FailureCategory.REPAIR_NOT_FOUND

    if result.solution_found and not result.final_compatible:
        return FailureCategory.INVALID_REPAIR

    if result.removed_mod_count > 0 and result.preservation_rate < 1.0:
        return FailureCategory.EXCESSIVE_REMOVALS

    return FailureCategory.OTHER
