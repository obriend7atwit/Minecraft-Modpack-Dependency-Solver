from __future__ import annotations

import csv
import json
import uuid
from contextlib import contextmanager
from pathlib import Path

from modpack_solver.evaluation import (
    evaluate_case,
    export_evaluation_csv,
    export_evaluation_json,
    load_evaluation_manifest,
    run_evaluation,
)
from modpack_solver.models import IssueType, RepairActionType
from modpack_solver.solver import CompatibilityStatus, SolverStatus


MANIFEST_PATH = Path("data/evaluation/manifest.json")


def test_one_valid_case_evaluates_successfully() -> None:
    result = evaluate_case(_manifest_spec("synthetic-valid"), manifest_path=MANIFEST_PATH)

    assert result.passed is True
    assert result.initial_status == CompatibilityStatus.COMPATIBLE
    assert result.solver_status == SolverStatus.ALREADY_COMPATIBLE


def test_one_repairable_invalid_case_evaluates_successfully() -> None:
    result = evaluate_case(_manifest_spec("synthetic-missing-dependency"), manifest_path=MANIFEST_PATH)

    assert result.passed is True
    assert result.initial_status == CompatibilityStatus.INCOMPATIBLE
    assert result.solver_status == SolverStatus.SOLUTION_FOUND
    assert RepairActionType.ADD_DEPENDENCY in result.action_types


def test_no_solution_expected_case_passes() -> None:
    result = evaluate_case(_manifest_spec("synthetic-no-solution"), manifest_path=MANIFEST_PATH)

    assert result.passed is True
    assert result.solver_status == SolverStatus.NO_SOLUTION


def test_search_limit_case_uses_manifest_limits() -> None:
    result = evaluate_case(_manifest_spec("synthetic-search-limit"), manifest_path=MANIFEST_PATH)

    assert result.passed is True
    assert result.solver_status == SolverStatus.LIMIT_REACHED


def test_expected_issue_types_are_required() -> None:
    spec = _manifest_spec("synthetic-missing-dependency").model_copy(
        update={"expected_issue_types": [IssueType.MISSING_DEPENDENCY, IssueType.HARD_CONFLICT]}
    )

    result = evaluate_case(spec, manifest_path=MANIFEST_PATH)

    assert result.passed is False
    assert result.issues_passed is False


def test_forbidden_issue_types_cause_failure() -> None:
    spec = _manifest_spec("synthetic-missing-dependency").model_copy(
        update={"forbidden_issue_types": [IssueType.MISSING_DEPENDENCY]}
    )

    result = evaluate_case(spec, manifest_path=MANIFEST_PATH)

    assert result.passed is False
    assert result.issues_passed is False


def test_cost_range_is_enforced() -> None:
    spec = _manifest_spec("synthetic-missing-dependency").model_copy(
        update={"expected_min_cost": 5, "expected_max_cost": 5}
    )

    result = evaluate_case(spec, manifest_path=MANIFEST_PATH)

    assert result.passed is False
    assert result.cost_passed is False


def test_preservation_threshold_is_enforced() -> None:
    spec = _manifest_spec("synthetic-hard-conflict").model_copy(
        update={"expected_min_preservation_rate": 1.0}
    )

    result = evaluate_case(spec, manifest_path=MANIFEST_PATH)

    assert result.passed is False
    assert result.preservation_passed is False


def test_complete_default_manifest_runs_offline() -> None:
    run = run_evaluation(MANIFEST_PATH)

    assert run.summary.total_cases == 25
    assert run.summary.failed_cases == 0


def test_json_export_works() -> None:
    with _workspace_temp_dir() as raw_tmp_path:
        tmp_path = Path(raw_tmp_path)
        run = run_evaluation(MANIFEST_PATH, max_cases=1)
        output_path = export_evaluation_json(run, tmp_path / "results.json")

        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert output_path.exists()
        assert "results" in payload
        assert "summary" in payload


def test_csv_export_works() -> None:
    with _workspace_temp_dir() as raw_tmp_path:
        tmp_path = Path(raw_tmp_path)
        run = run_evaluation(MANIFEST_PATH, max_cases=1)
        output_path = export_evaluation_csv(run, tmp_path / "results.csv")

        with output_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        assert output_path.exists()
        assert rows
        assert rows[0]["case_id"]


def test_failed_expectation_still_produces_result_and_failure_reason() -> None:
    spec = _manifest_spec("synthetic-valid").model_copy(
        update={"expected_action_types": [RepairActionType.REMOVE_MOD]}
    )

    result = evaluate_case(spec, manifest_path=MANIFEST_PATH)

    assert result.passed is False
    assert result.failure_reasons


def test_case_selection_by_id_works() -> None:
    run = run_evaluation(MANIFEST_PATH, case_ids={"synthetic-valid", "synthetic-no-solution"})

    assert [result.case_id for result in run.results] == ["synthetic-valid", "synthetic-no-solution"]


def test_max_cases_works() -> None:
    run = run_evaluation(MANIFEST_PATH, max_cases=2)

    assert len(run.results) == 2


def test_manifest_order_is_preserved() -> None:
    specs = load_evaluation_manifest(MANIFEST_PATH)
    run = run_evaluation(MANIFEST_PATH, case_ids={specs[1].case_id, specs[0].case_id})

    assert [result.case_id for result in run.results] == [specs[0].case_id, specs[1].case_id]


def _manifest_spec(case_id: str):
    for spec in load_evaluation_manifest(MANIFEST_PATH):
        if spec.case_id == case_id:
            return spec
    raise AssertionError(f"Case ID '{case_id}' was not found in the manifest.")


@contextmanager
def _workspace_temp_dir():
    root = Path(".test-artifacts") / "pytest-temp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    yield path
