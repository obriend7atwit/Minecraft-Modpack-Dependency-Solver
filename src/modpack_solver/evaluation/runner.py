"""Manifest loading, case evaluation, and export helpers."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from modpack_solver.evaluation.metrics import preservation_rate, summarize_results
from modpack_solver.evaluation.models import EvaluationCaseResult, EvaluationCaseSpec, EvaluationRun
from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.models import RepairAction
from modpack_solver.solver import RepairWeights, SearchLimits, SolverStatus, solve_weighted_case
from modpack_solver.solver.checker import IssueSeverity, check_graph
from modpack_solver.solver.explanations import build_explanation_report
from modpack_solver.solver.state import count_original_mods_preserved, count_removed_original_mods


def load_evaluation_manifest(path: str | Path) -> list[EvaluationCaseSpec]:
    """Load and validate an evaluation manifest."""

    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Evaluation manifest '{manifest_path}' was not found.")

    try:
        raw_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Evaluation manifest '{manifest_path}' is not valid JSON.") from exc

    if not isinstance(raw_data, list):
        raise ValueError("Evaluation manifest must contain a top-level JSON list.")

    seen_case_ids: set[str] = set()
    specs: list[EvaluationCaseSpec] = []
    for entry in raw_data:
        try:
            spec = EvaluationCaseSpec.model_validate(entry)
        except ValidationError as exc:
            raise ValueError(f"Invalid evaluation manifest entry: {exc}") from exc
        if spec.case_id in seen_case_ids:
            raise ValueError(f"Duplicate evaluation case ID '{spec.case_id}' in manifest.")
        seen_case_ids.add(spec.case_id)

        fixture_path = _resolve_fixture_path(spec.fixture, manifest_path)
        if not fixture_path.exists():
            raise FileNotFoundError(
                f"Fixture '{spec.fixture}' for evaluation case '{spec.case_id}' was not found."
            )
        specs.append(spec.model_copy(update={"fixture": str(fixture_path)}))

    return specs


def evaluate_case(
    spec: EvaluationCaseSpec,
    *,
    manifest_path: str | Path,
    weights: RepairWeights | None = None,
) -> EvaluationCaseResult:
    """Run one evaluation case through the existing graph, checker, solver, and explanation pipeline."""

    fixture_path = _resolve_fixture_path(spec.fixture, Path(manifest_path))
    case = load_synthetic_case(fixture_path)
    graph_result = build_graph_from_synthetic_case(case)
    initial_report = check_graph(graph_result)
    solver_result = solve_weighted_case(
        case,
        weights=weights or RepairWeights(),
        limits=spec.search_limits or SearchLimits(),
        max_solutions=4,
    )
    explanation_report = build_explanation_report(
        case=case,
        graph_result=graph_result,
        initial_report=initial_report,
        solver_result=solver_result,
        max_alternatives=3,
    )

    initial_issue_types = _unique_issue_types(initial_report)
    action_types = _unique_action_types(solver_result.actions)
    original_mod_count = len({selected.mod_id for selected in case.config.selected_mods})
    reference_config = solver_result.repaired_config or solver_result.best_partial_config or case.config
    preserved = count_original_mods_preserved(case.config, reference_config)
    removed = count_removed_original_mods(case.config, reference_config)
    preservation = preservation_rate(original_mod_count, preserved)
    final_compatible = bool(
        solver_result.final_report
        and not any(issue.severity == IssueSeverity.ERROR.value for issue in solver_result.final_report.issues)
    )

    status_passed = (
        initial_report.status == spec.expected_initial_status
        and solver_result.status == spec.expected_solver_status
    )
    issues_passed = all(issue_type in initial_issue_types for issue_type in spec.expected_issue_types) and all(
        issue_type not in initial_issue_types for issue_type in spec.forbidden_issue_types
    )
    actions_passed = all(action_type in action_types for action_type in spec.expected_action_types)
    cost_passed = _cost_in_range(solver_result.total_cost, spec.expected_min_cost, spec.expected_max_cost)
    preservation_passed = spec.expected_min_preservation_rate is None or preservation >= spec.expected_min_preservation_rate
    final_compatibility_passed = True if not spec.expected_final_compatible else final_compatible
    exact_issue_match = set(initial_issue_types) == set(spec.expected_issue_types)

    relevant_issue_explanations = [
        explanation
        for explanation in explanation_report.issue_explanations
        if explanation.issue_type in spec.expected_issue_types
    ]
    explanation_root_cause_present = bool(explanation_report.issue_explanations) or not spec.expected_issue_types
    explanation_affected_mods_present = (
        all(bool(explanation.affected_mod_ids) for explanation in relevant_issue_explanations)
        if relevant_issue_explanations
        else True
    )
    explanation_repair_present = True
    if spec.expected_solver_status == SolverStatus.SOLUTION_FOUND:
        explanation_repair_present = (
            explanation_report.repair_explanation is not None
            and bool(explanation_report.repair_explanation.selected_actions)
        )
    chain_expected = "chain" in spec.case_id and bool(spec.expected_issue_types)
    explanation_chain_present_when_expected = True
    if chain_expected:
        explanation_chain_present_when_expected = any(
            explanation.dependency_chain for explanation in explanation_report.issue_explanations
        )

    failure_reasons = _failure_reasons(
        status_passed=status_passed,
        issues_passed=issues_passed,
        actions_passed=actions_passed,
        cost_passed=cost_passed,
        preservation_passed=preservation_passed,
        final_compatibility_passed=final_compatibility_passed,
        explanation_root_cause_present=explanation_root_cause_present,
        explanation_affected_mods_present=explanation_affected_mods_present,
        explanation_repair_present=explanation_repair_present,
        explanation_chain_present_when_expected=explanation_chain_present_when_expected,
        spec=spec,
        initial_status=initial_report.status.value,
        solver_status=solver_result.status.value,
    )
    passed = not failure_reasons

    return EvaluationCaseResult(
        case_id=spec.case_id,
        name=spec.name,
        source_type=spec.source_type,
        expected_initial_status=spec.expected_initial_status,
        expected_solver_status=spec.expected_solver_status,
        expected_issue_types=list(spec.expected_issue_types),
        initial_status=initial_report.status,
        solver_status=solver_result.status,
        initial_issue_types=initial_issue_types,
        action_types=action_types,
        final_compatible=final_compatible,
        total_cost=solver_result.total_cost,
        action_count=len(solver_result.actions),
        original_mods_preserved=preserved,
        original_mod_count=original_mod_count,
        preservation_rate=preservation,
        removed_mod_count=removed,
        runtime_seconds=solver_result.runtime_seconds,
        states_expanded=solver_result.states_expanded,
        status_passed=status_passed,
        issues_passed=issues_passed,
        actions_passed=actions_passed,
        cost_passed=cost_passed,
        preservation_passed=preservation_passed,
        final_compatibility_passed=final_compatibility_passed,
        exact_issue_match=exact_issue_match,
        passed=passed,
        explanation_root_cause_present=explanation_root_cause_present,
        explanation_affected_mods_present=explanation_affected_mods_present,
        explanation_repair_present=explanation_repair_present,
        explanation_chain_present_when_expected=explanation_chain_present_when_expected,
        failure_reasons=failure_reasons,
    )


def run_evaluation(
    manifest_path: str | Path,
    *,
    weights: RepairWeights | None = None,
    case_ids: set[str] | None = None,
    max_cases: int | None = None,
) -> EvaluationRun:
    """Run an offline evaluation across selected manifest cases."""

    specs = load_evaluation_manifest(manifest_path)
    if case_ids is not None:
        specs = [spec for spec in specs if spec.case_id in case_ids]
    if max_cases is not None:
        specs = specs[:max_cases]

    results: list[EvaluationCaseResult] = []
    for spec in specs:
        results.append(evaluate_case(spec, manifest_path=manifest_path, weights=weights))

    return EvaluationRun(
        manifest_path=str(Path(manifest_path)),
        results=results,
        summary=summarize_results(results),
    )


def export_evaluation_json(run: EvaluationRun, path: str | Path) -> Path:
    """Export an evaluation run as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(run.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


def export_evaluation_csv(run: EvaluationRun, path: str | Path) -> Path:
    """Export one row per evaluation case as CSV."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "name",
        "source_type",
        "initial_status",
        "solver_status",
        "issue_types",
        "action_types",
        "final_compatible",
        "total_cost",
        "preservation_rate",
        "removed_mod_count",
        "runtime_seconds",
        "states_expanded",
        "passed",
        "failure_reasons",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in run.results:
            writer.writerow(
                {
                    "case_id": result.case_id,
                    "name": result.name,
                    "source_type": result.source_type.value,
                    "initial_status": result.initial_status.value,
                    "solver_status": result.solver_status.value,
                    "issue_types": "|".join(issue_type.value for issue_type in result.initial_issue_types),
                    "action_types": "|".join(action_type.value for action_type in result.action_types),
                    "final_compatible": result.final_compatible,
                    "total_cost": result.total_cost if result.total_cost is not None else "",
                    "preservation_rate": f"{result.preservation_rate:.4f}",
                    "removed_mod_count": result.removed_mod_count,
                    "runtime_seconds": f"{result.runtime_seconds:.6f}",
                    "states_expanded": result.states_expanded,
                    "passed": result.passed,
                    "failure_reasons": " | ".join(result.failure_reasons),
                }
            )
    return output_path


def _resolve_fixture_path(fixture: str, manifest_path: Path) -> Path:
    fixture_path = Path(fixture)
    if fixture_path.is_absolute():
        return fixture_path
    base_dir = manifest_path.parent if manifest_path.suffix else manifest_path
    return (base_dir / fixture_path).resolve()


def _unique_issue_types(report) -> list:
    seen = set()
    ordered = []
    for issue in report.issues:
        if issue.issue_type in seen:
            continue
        seen.add(issue.issue_type)
        ordered.append(issue.issue_type)
    return ordered


def _unique_action_types(actions: list[RepairAction]) -> list:
    seen = set()
    ordered = []
    for action in actions:
        if action.action_type in seen:
            continue
        seen.add(action.action_type)
        ordered.append(action.action_type)
    return ordered


def _cost_in_range(cost: int | None, minimum: int | None, maximum: int | None) -> bool:
    if minimum is None and maximum is None:
        return True
    if cost is None:
        return False
    if minimum is not None and cost < minimum:
        return False
    if maximum is not None and cost > maximum:
        return False
    return True


def _failure_reasons(**kwargs: Any) -> list[str]:
    reasons: list[str] = []
    spec = kwargs["spec"]
    if not kwargs["status_passed"]:
        reasons.append(
            f"Expected statuses ({spec.expected_initial_status.value}, {spec.expected_solver_status.value}) "
            f"but got ({kwargs['initial_status']}, {kwargs['solver_status']})."
        )
    if not kwargs["issues_passed"]:
        reasons.append("Expected issue-type requirements were not satisfied.")
    if not kwargs["actions_passed"]:
        reasons.append("Expected action types were not present in the weighted repair.")
    if not kwargs["cost_passed"]:
        reasons.append("Weighted repair cost fell outside the expected range.")
    if not kwargs["preservation_passed"]:
        reasons.append("Preservation rate fell below the expected threshold.")
    if not kwargs["final_compatibility_passed"]:
        reasons.append("Final compatibility expectation was not satisfied.")
    if not kwargs["explanation_root_cause_present"]:
        reasons.append("Root-cause explanations were not produced.")
    if not kwargs["explanation_affected_mods_present"]:
        reasons.append("Affected mod IDs were not present in structured explanations.")
    if not kwargs["explanation_repair_present"]:
        reasons.append("Repair explanation details were not present.")
    if not kwargs["explanation_chain_present_when_expected"]:
        reasons.append("Expected dependency-chain explanation was not present.")
    return reasons
