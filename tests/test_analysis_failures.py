from __future__ import annotations

from modpack_solver.analysis import ExperimentCaseResult, ExperimentSystem, FailureCategory, RuntimeMeasurements, classify_failure
from modpack_solver.evaluation.models import EvaluationCaseSpec, EvaluationSourceType
from modpack_solver.models import IssueType
from modpack_solver.solver import SolverStatus
from modpack_solver.solver.checker import CompatibilityStatus


def test_incorrect_issue_detection_is_classified() -> None:
    result = _result(issue_detection_correct=False)

    assert classify_failure(_spec(), result) == FailureCategory.INCORRECT_ISSUE_DETECTION


def test_repair_not_found_is_classified() -> None:
    result = _result(repair_expected=True, issue_detection_correct=True, repair_outcome_correct=False)

    assert classify_failure(_spec(), result) == FailureCategory.REPAIR_NOT_FOUND


def test_invalid_repair_is_classified() -> None:
    result = _result(solution_found=True, final_compatible=False, repair_outcome_correct=False)

    assert classify_failure(_spec(), result) == FailureCategory.INVALID_REPAIR


def test_missing_metadata_is_classified() -> None:
    result = _result(issue_types=[IssueType.UNKNOWN_DEPENDENCY_TARGET], repair_outcome_correct=False)

    assert classify_failure(_spec(), result) == FailureCategory.MISSING_METADATA


def test_unsupported_version_is_classified() -> None:
    result = _result(failure_detail="Unsupported version format caused a skipped candidate.")

    assert classify_failure(_spec(), result) == FailureCategory.UNSUPPORTED_VERSION_FORMAT


def test_higher_cost_repair_is_classified() -> None:
    result = _result(failure_detail="Higher cost repair was selected.")

    assert classify_failure(_spec(), result) == FailureCategory.HIGHER_COST_REPAIR


def test_non_executable_baseline_is_classified() -> None:
    result = _result(system=ExperimentSystem.BASELINE, suggestion_count=1, executable_suggestion_count=0)

    assert classify_failure(_spec(), result) == FailureCategory.NON_EXECUTABLE_BASELINE


def test_expected_no_solution_is_not_failure() -> None:
    spec = _spec(expected_solver_status=SolverStatus.NO_SOLUTION)
    result = _result(no_solution_expected=True, repair_outcome_correct=True)

    assert classify_failure(spec, result) is None


def test_successful_case_returns_no_failure() -> None:
    result = _result(status_correct=True, issue_detection_correct=True, repair_outcome_correct=True)

    assert classify_failure(_spec(), result) is None


def _spec(expected_solver_status: SolverStatus = SolverStatus.SOLUTION_FOUND) -> EvaluationCaseSpec:
    return EvaluationCaseSpec(
        case_id="case",
        name="Case",
        fixture="data/synthetic/valid_modpack.json",
        source_type=EvaluationSourceType.SYNTHETIC,
        expected_initial_status=CompatibilityStatus.INCOMPATIBLE,
        expected_solver_status=expected_solver_status,
        expected_issue_types=[IssueType.MISSING_DEPENDENCY],
    )


def _result(**updates) -> ExperimentCaseResult:
    base = {
        "case_id": "case",
        "name": "Case",
        "source_type": EvaluationSourceType.SYNTHETIC,
        "system": ExperimentSystem.WEIGHTED_DEFAULT,
        "profile_id": "default",
        "repair_expected": False,
        "solution_found": False,
        "final_compatible": False,
        "issue_types": [IssueType.MISSING_DEPENDENCY],
        "runtime": RuntimeMeasurements(samples_seconds=[0.0], median_seconds=0.0),
        "status_correct": True,
        "issue_detection_correct": True,
        "repair_outcome_correct": False,
    }
    base.update(updates)
    return ExperimentCaseResult(**base)
