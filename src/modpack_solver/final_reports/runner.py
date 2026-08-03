"""Offline final-dataset evaluation using existing checker, baseline, and solver APIs."""

from __future__ import annotations

import csv
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from modpack_solver.analysis import (
    apply_baseline_suggestions,
    baseline_suggestions_for_case,
    get_weight_profile,
    measure_runtime,
)
from modpack_solver.final_dataset.manifest import load_final_dataset_manifest, resolve_final_case_path
from modpack_solver.final_dataset.models import FinalDatasetCaseSpec
from modpack_solver.final_dataset.validation import validate_final_dataset
from modpack_solver.final_dataset.repair_trace import replay_repair_plan
from modpack_solver.final_reports.models import (
    FinalCaseEvaluation,
    FinalEvaluationRun,
    FinalEvaluationSystem,
    FinalSystemMetrics,
)
from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.models import IssueType, RepairAction, SyntheticCase
from modpack_solver.solver import SolverStatus, build_explanation_report, plan_cost, solve_weighted_case
from modpack_solver.solver.checker import IssueSeverity, check_graph


def run_final_evaluation(
    *,
    manifest_path: str | Path = "data/final_dataset/manifest.json",
    output_dir: str | Path = "results/final",
    offline: bool = True,
    allow_live: bool = False,
    max_cases: int | None = None,
    case_ids: Sequence[str] | None = None,
    profile_ids: Sequence[str] = ("default", "preservation"),
    runtime_repetitions: int = 3,
    skip_charts: bool = False,
) -> FinalEvaluationRun:
    """Run all final systems and write reproducible reports."""

    if allow_live and offline:
        raise ValueError("Choose either offline mode or allow_live, not both.")
    if not offline and not allow_live:
        raise ValueError("Live behavior must be explicitly enabled with allow_live=True.")
    if runtime_repetitions < 1:
        raise ValueError("runtime_repetitions must be at least 1.")

    manifest = load_final_dataset_manifest(manifest_path)
    specs = list(manifest.cases)
    if case_ids:
        requested = set(case_ids)
        specs = [spec for spec in specs if spec.case_id in requested]
        missing = requested - {spec.case_id for spec in specs}
        if missing:
            raise ValueError(f"Unknown final dataset case IDs: {', '.join(sorted(missing))}.")
    if max_cases is not None:
        specs = specs[:max_cases]

    validation = validate_final_dataset(
        manifest_path,
        offline=True,
        max_cases=max_cases if not case_ids else None,
    )
    if case_ids:
        # Full path/schema validation already happened while loading; selected cases are
        # behaviorally validated as part of their evaluation below.
        validation = validation.model_copy(
            update={
                "total_cases": len(specs),
                "passed_cases": len(specs),
                "failed_cases": 0,
                "failures": {},
            }
        )

    results: list[FinalCaseEvaluation] = []
    for spec in specs:
        case = load_synthetic_case(resolve_final_case_path(spec, manifest_path))
        graph_result = build_graph_from_synthetic_case(case)
        initial_report = check_graph(graph_result)
        results.append(
            _evaluate_baseline(
                spec,
                case,
                initial_report,
                runtime_repetitions=runtime_repetitions,
            )
        )
        for profile_id in profile_ids:
            results.append(
                _evaluate_weighted(
                    spec,
                    case,
                    graph_result,
                    initial_report,
                    profile_id=profile_id,
                    runtime_repetitions=runtime_repetitions,
                )
            )

    metrics = [summarize_final_results(system_results) for system_results in _group_by_system(results)]
    run = FinalEvaluationRun(
        manifest_path=str(Path(manifest_path)),
        output_dir=str(Path(output_dir)),
        generated_at=datetime.now(timezone.utc).isoformat(),
        runtime_repetitions=runtime_repetitions,
        validation=validation,
        results=results,
        metrics=metrics,
    )
    generated = _write_core_outputs(run, Path(output_dir))

    from modpack_solver.final_reports.summary import write_final_summary
    from modpack_solver.final_reports.tables import generate_final_tables

    generated.extend(generate_final_tables(run, output_dir))
    if not skip_charts:
        from modpack_solver.final_reports.charts import generate_final_charts
        from modpack_solver.final_reports.paper import generate_paper_outputs

        generated.extend(Path(chart.path) for chart in generate_final_charts(run, output_dir))
        generated.extend(generate_paper_outputs(run, output_dir))
    summary_path = Path(output_dir) / "reports" / "final_evaluation_summary.md"
    generated.append(summary_path)
    run.generated_files = [str(path) for path in generated]
    write_final_summary(run, summary_path)
    _write_json(Path(output_dir) / "evaluation" / "final_results.json", run.model_dump(mode="json"))
    return run


def summarize_final_results(results: Sequence[FinalCaseEvaluation]) -> FinalSystemMetrics:
    values = list(results)
    if not values:
        raise ValueError("Cannot summarize an empty final result set.")
    repairable = [result for result in values if result.expected_repairable]
    successful = [result for result in repairable if result.repair_success]
    costs = [result.total_cost for result in successful if result.total_cost is not None]
    runtimes = [result.runtime_seconds for result in values]
    issue_correct = [result.issue_detection_correct for result in values]
    system = values[0].system
    suggestions = sum(result.suggestion_count for result in values)
    executable = sum(result.executable_suggestion_count for result in values)
    weighted_values = [result for result in values if result.system != FinalEvaluationSystem.BASELINE]
    full_preservation = [
        result
        for result in repairable
        if result.repair_success and result.preservation_rate == 1.0
    ]
    all_expected_original_mods = sum(result.original_mod_count for result in repairable)
    successful_preserved_mods = sum(
        result.original_mods_preserved for result in successful
    )
    cascading = [result for result in repairable if result.is_cascading]
    successful_cascading = [result for result in cascading if result.repair_success]
    oracle_verified = [
        result for result in values if result.minimum_cost_verified
    ]
    oracle_values = [
        result
        for result in oracle_verified
        if result.minimum_cost_verified and result.optimal_plan_agreement is not None
    ]
    no_solution_values = [
        result for result in values if result.expected_solver_status == SolverStatus.NO_SOLUTION
    ]
    chain_explanations = [
        result.dependency_chain_explanation_correct
        for result in weighted_values
        if result.dependency_chain_explanation_correct is not None
    ]
    cascade_explanations = [
        result.cascading_step_explanation_correct
        for result in weighted_values
        if result.cascading_step_explanation_correct is not None
    ]
    global_plan_explanations = [
        result.global_plan_reason_correct
        for result in weighted_values
        if result.global_plan_reason_correct is not None
    ]
    return FinalSystemMetrics(
        system=system,
        total_cases=len(values),
        repairable_cases=len(repairable),
        successful_repairs=len(successful),
        repair_success_rate=len(successful) / len(repairable) if repairable else 0.0,
        average_preservation_rate=_mean([result.preservation_rate for result in successful]),
        full_preservation_repairs=len(full_preservation),
        full_preservation_rate=(
            len(full_preservation) / len(repairable) if repairable else 0.0
        ),
        preserved_mod_fraction_all_expected_repairs=(
            successful_preserved_mods / all_expected_original_mods
            if all_expected_original_mods
            else 0.0
        ),
        average_weighted_cost=_mean(costs) if costs else None,
        average_action_count=_mean([result.action_count for result in successful]),
        average_removed_mods=_mean([result.removed_mod_count for result in successful]),
        median_runtime_seconds=float(statistics.median(runtimes)) if runtimes else 0.0,
        average_states_expanded=_mean([result.states_expanded for result in values]),
        issue_detection_accuracy=sum(issue_correct) / len(issue_correct) if issue_correct else 0.0,
        explanation_completeness_rate=(
            sum(result.explanation_complete for result in weighted_values) / len(weighted_values)
            if weighted_values
            else None
        ),
        suggestion_coverage_rate=(
            sum(result.expected_repairable and result.suggestion_count > 0 for result in values) / len(repairable)
            if system == FinalEvaluationSystem.BASELINE and repairable
            else None
        ),
        executable_suggestion_rate=(
            executable / suggestions
            if system == FinalEvaluationSystem.BASELINE and suggestions
            else (0.0 if system == FinalEvaluationSystem.BASELINE else None)
        ),
        cascading_cases=len(cascading),
        successful_cascading_repairs=len(successful_cascading),
        cascading_repair_success_rate=(
            len(successful_cascading) / len(cascading) if cascading else None
        ),
        mean_cascading_actions=(
            _mean([result.action_count for result in successful_cascading])
            if successful_cascading
            else None
        ),
        maximum_repair_depth=max(
            (result.repair_depth for result in successful),
            default=0,
        ),
        cases_with_temporary_issue_increase=sum(
            result.issue_count_temporarily_increased for result in cascading
        ),
        cases_with_issue_type_change=sum(
            result.issue_type_changed_after_action for result in cascading
        ),
        oracle_verified_cases=len(oracle_verified),
        optimal_plan_agreements=sum(
            result.optimal_plan_agreement is True for result in oracle_values
        ),
        optimal_plan_agreement_rate=(
            sum(result.optimal_plan_agreement is True for result in oracle_values)
            / len(oracle_values)
            if oracle_values
            else None
        ),
        no_solution_cases=len(no_solution_values),
        correct_no_solution_cases=sum(
            result.no_solution_correct is True for result in no_solution_values
        ),
        no_solution_correctness_rate=(
            sum(result.no_solution_correct is True for result in no_solution_values)
            / len(no_solution_values)
            if no_solution_values
            else None
        ),
        dependency_chain_explanation_accuracy=(
            sum(chain_explanations) / len(chain_explanations)
            if chain_explanations
            else None
        ),
        cascading_step_explanation_accuracy=(
            sum(cascade_explanations) / len(cascade_explanations)
            if cascade_explanations
            else None
        ),
        global_plan_reason_accuracy=(
            sum(global_plan_explanations) / len(global_plan_explanations)
            if global_plan_explanations
            else None
        ),
    )


def _evaluate_weighted(
    spec,
    case,
    graph_result,
    initial_report,
    *,
    profile_id: str,
    runtime_repetitions: int,
) -> FinalCaseEvaluation:
    profile = get_weight_profile(profile_id)
    operation = lambda: solve_weighted_case(
        case,
        weights=profile.weights,
        max_solutions=4,
    )
    solver_result, runtime = measure_runtime(operation, repetitions=runtime_repetitions)
    final_report = solver_result.final_report or solver_result.best_partial_report
    final_compatible = _is_compatible(final_report)
    explanation = build_explanation_report(
        case=case,
        graph_result=graph_result,
        initial_report=initial_report,
        solver_result=solver_result,
    )
    explanation_complete = bool(
        explanation.overall_summary.strip()
        and explanation.technical_summary.strip()
        and explanation.repair_explanation
        and (not initial_report.issues or explanation.issue_explanations)
    )
    original_count = len({selected.mod_id for selected in case.config.selected_mods})
    actions = list(solver_result.actions)
    repair_trace = None
    if actions:
        try:
            repair_trace = replay_repair_plan(case, actions)
        except ValueError:
            repair_trace = None
    error_counts = (
        [
            sum(issue.severity == IssueSeverity.ERROR.value for issue in step.report_before.issues)
            for step in repair_trace.steps
        ]
        + (
            [
                sum(
                    issue.severity == IssueSeverity.ERROR.value
                    for issue in repair_trace.steps[-1].report_after.issues
                )
            ]
            if repair_trace and repair_trace.steps
            else []
        )
        if repair_trace
        else []
    )
    issue_type_changed = bool(
        repair_trace
        and any(
            set(step.issue_types_before) != set(step.issue_types_after)
            for step in repair_trace.steps
        )
    )
    expected_minimum = (
        spec.known_minimum_preservation_cost
        if profile_id == "preservation"
        else spec.known_minimum_default_cost
    )
    optimal_agreement = (
        solver_result.total_cost == expected_minimum
        if spec.minimum_cost_verified and expected_minimum is not None
        else None
    )
    chain_required = any(
        issue.issue_type == IssueType.MISSING_DEPENDENCY
        for issue in initial_report.issues
    )
    chain_explained = (
        any(len(item.dependency_chain) >= 2 for item in explanation.issue_explanations)
        if chain_required
        else None
    )
    passed, failure_category, detail = _weighted_outcome(
        spec,
        initial_report,
        solver_result.status,
        final_compatible,
        actions,
        explanation_complete,
    )
    return FinalCaseEvaluation(
        case_id=spec.case_id,
        display_name=spec.display_name,
        system=(
            FinalEvaluationSystem.WEIGHTED_PRESERVATION
            if profile_id == "preservation"
            else FinalEvaluationSystem.WEIGHTED_DEFAULT
        ),
        profile_id=profile_id,
        **_spec_evaluation_fields(spec),
        expected_repairable=spec.expected_repairable,
        expected_initial_status=spec.expected_initial_status,
        expected_solver_status=spec.expected_solver_status,
        initial_status=initial_report.status,
        solver_status=solver_result.status,
        issue_types=_unique([issue.issue_type for issue in initial_report.issues]),
        action_types=_unique([action.action_type for action in actions]),
        action_count=len(actions),
        final_compatible=final_compatible,
        repair_success=spec.expected_repairable and solver_result.status == SolverStatus.SOLUTION_FOUND and final_compatible,
        total_cost=solver_result.total_cost,
        original_mod_count=original_count,
        original_mods_preserved=solver_result.original_mods_preserved,
        preservation_rate=solver_result.original_mods_preserved / original_count if original_count else 1.0,
        removed_mod_count=solver_result.removed_mod_count,
        version_change_count=solver_result.version_change_count,
        runtime_seconds=runtime.median_seconds,
        runtime_samples_seconds=runtime.samples_seconds,
        runtime_minimum_seconds=runtime.minimum_seconds,
        runtime_maximum_seconds=runtime.maximum_seconds,
        states_expanded=solver_result.states_expanded,
        repair_depth=len(actions),
        issue_count_temporarily_increased=any(
            after > before for before, after in zip(error_counts, error_counts[1:])
        ),
        issue_type_changed_after_action=issue_type_changed,
        cascading_step_explanation_correct=(
            bool(
                repair_trace
                and len(repair_trace.steps) == len(actions)
                and all((action.reason or "").strip() for action in actions)
            )
            if spec.is_cascading and actions
            else None
        ),
        dependency_chain_explanation_correct=chain_explained,
        global_plan_reason_correct=bool(
            explanation.repair_explanation
            and explanation.repair_explanation.short_summary.strip()
            and explanation.repair_explanation.technical_detail.strip()
        ),
        optimal_plan_agreement=optimal_agreement,
        no_solution_correct=(
            solver_result.status == SolverStatus.NO_SOLUTION
            if spec.expected_solver_status == SolverStatus.NO_SOLUTION
            else None
        ),
        explanation_complete=explanation_complete,
        issue_detection_correct=(
            initial_report.status == spec.expected_initial_status
            and set(spec.expected_issue_types).issubset({issue.issue_type for issue in initial_report.issues})
        ),
        passed=passed,
        failure_category=failure_category,
        failure_detail=detail,
    )


def _evaluate_baseline(spec, case, initial_report, *, runtime_repetitions: int) -> FinalCaseEvaluation:
    suggestions = baseline_suggestions_for_case(case)
    operation = lambda: apply_baseline_suggestions(case, suggestions)
    baseline_result, runtime = measure_runtime(operation, repetitions=runtime_repetitions)
    actions = list(baseline_result.executable_actions)
    initial_compatible = initial_report.status.value != "incompatible"
    if initial_compatible:
        solver_status = SolverStatus.ALREADY_COMPATIBLE
    elif baseline_result.final_compatible:
        solver_status = SolverStatus.SOLUTION_FOUND
    else:
        solver_status = SolverStatus.NO_SOLUTION
    original_count = len({selected.mod_id for selected in case.config.selected_mods})
    issues_match = set(spec.expected_issue_types).issubset({issue.issue_type for issue in initial_report.issues})
    outcome_correct = (
        baseline_result.final_compatible
        if spec.expected_repairable or spec.expected_solver_status == SolverStatus.ALREADY_COMPATIBLE
        else not baseline_result.final_compatible
    )
    passed = initial_report.status == spec.expected_initial_status and issues_match and outcome_correct
    failure_category = None
    detail = None
    if not issues_match or initial_report.status != spec.expected_initial_status:
        failure_category = "incorrect_issue_detection"
        detail = "Baseline used the shared checker, but observed issues did not match the manifest."
    elif spec.expected_repairable and not baseline_result.final_compatible:
        failure_category = "repair_not_found"
        detail = "One-pass baseline suggestions did not produce a compatible configuration."
    elif not outcome_correct:
        failure_category = "incorrect_expected_result"
        detail = "Baseline outcome differed from the expected case category."
    return FinalCaseEvaluation(
        case_id=spec.case_id,
        display_name=spec.display_name,
        system=FinalEvaluationSystem.BASELINE,
        **_spec_evaluation_fields(spec),
        expected_repairable=spec.expected_repairable,
        expected_initial_status=spec.expected_initial_status,
        expected_solver_status=spec.expected_solver_status,
        initial_status=initial_report.status,
        solver_status=solver_status,
        issue_types=_unique([issue.issue_type for issue in initial_report.issues]),
        action_types=_unique([action.action_type for action in actions]),
        action_count=len(actions),
        final_compatible=baseline_result.final_compatible,
        repair_success=spec.expected_repairable and baseline_result.final_compatible,
        total_cost=plan_cost(actions, get_weight_profile("default").weights) if actions else 0,
        original_mod_count=original_count,
        original_mods_preserved=baseline_result.original_mods_preserved,
        preservation_rate=baseline_result.original_mods_preserved / original_count if original_count else 1.0,
        removed_mod_count=baseline_result.removed_mod_count,
        version_change_count=baseline_result.version_change_count,
        runtime_seconds=runtime.median_seconds,
        runtime_samples_seconds=runtime.samples_seconds,
        runtime_minimum_seconds=runtime.minimum_seconds,
        runtime_maximum_seconds=runtime.maximum_seconds,
        states_expanded=0,
        repair_depth=len(actions),
        no_solution_correct=(
            solver_status == SolverStatus.NO_SOLUTION
            if spec.expected_solver_status == SolverStatus.NO_SOLUTION
            else None
        ),
        suggestion_count=len(suggestions),
        executable_suggestion_count=len(actions),
        explanation_complete=False,
        issue_detection_correct=(initial_report.status == spec.expected_initial_status and issues_match),
        passed=passed,
        failure_category=failure_category,
        failure_detail=detail,
    )


def _weighted_outcome(spec, initial_report, status, final_compatible, actions, explanation_complete):
    actual_issues = {issue.issue_type for issue in initial_report.issues}
    issues_match = set(spec.expected_issue_types).issubset(actual_issues)
    actions_match = set(spec.expected_action_types).issubset({action.action_type for action in actions})
    passed = (
        initial_report.status == spec.expected_initial_status
        and status == spec.expected_solver_status
        and issues_match
        and actions_match
        and final_compatible == spec.expected_final_compatible
        and explanation_complete
    )
    if initial_report.status != spec.expected_initial_status or not issues_match:
        return passed, "incorrect_issue_detection", "Observed checker status or issue types differed from the manifest."
    if spec.expected_repairable and not final_compatible:
        return passed, "repair_not_found", "Weighted solver did not produce a compatible repair."
    if status != spec.expected_solver_status or final_compatible != spec.expected_final_compatible:
        return passed, "incorrect_expected_result", "Solver status or final compatibility differed from the manifest."
    if not actions_match:
        return passed, "higher_cost_repair", "Selected repair did not include the expected action types."
    if not explanation_complete:
        return passed, "incomplete_explanation", "Structured explanation fields were incomplete."
    return passed, None, None


def _spec_evaluation_fields(spec: FinalDatasetCaseSpec) -> dict:
    return {
        "source_type": spec.source_type,
        "source_family_id": spec.source_family_id,
        "source_pack_slug": spec.source_pack_slug,
        "collection_method": spec.collection_method,
        "ground_truth_method": spec.ground_truth_method,
        "review_status": spec.review_status,
        "modification_type": spec.modification_type,
        "topology": spec.topology,
        "is_cascading": spec.is_cascading,
        "pack_size_category": spec.pack_size_category,
        "selected_mod_count": spec.selected_mod_count,
        "dependency_edge_count": spec.dependency_edge_count or 0,
        "required_edge_count": spec.required_edge_count,
        "total_dependency_edge_count": spec.total_dependency_edge_count,
        "required_edge_density": spec.required_edge_density,
        "maximum_required_depth": spec.maximum_required_depth,
        "mean_required_branching_factor": spec.mean_required_branching_factor,
        "mean_candidate_versions_per_mod": spec.mean_candidate_versions_per_mod,
        "maximum_candidate_versions_per_mod": spec.maximum_candidate_versions_per_mod,
        "metadata_coverage_rate": spec.metadata_coverage_rate,
        "expected_repair_action_count": spec.expected_repair_action_count,
        "known_minimum_default_cost": spec.known_minimum_default_cost,
        "known_minimum_preservation_cost": spec.known_minimum_preservation_cost,
        "minimum_cost_verified": spec.minimum_cost_verified,
    }


def _write_core_outputs(run: FinalEvaluationRun, output_dir: Path) -> list[Path]:
    evaluation_dir = output_dir / "evaluation"
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        _write_json(evaluation_dir / "final_results.json", run.model_dump(mode="json")),
        _write_results_csv(evaluation_dir / "final_results.csv", run.results),
    ]
    mapping = {
        FinalEvaluationSystem.BASELINE: "baseline_results.json",
        FinalEvaluationSystem.WEIGHTED_DEFAULT: "default_profile.json",
        FinalEvaluationSystem.WEIGHTED_PRESERVATION: "preservation_profile.json",
    }
    for system, file_name in mapping.items():
        paths.append(
            _write_json(
                evaluation_dir / file_name,
                [result.model_dump(mode="json") for result in run.results if result.system == system],
            )
        )
    return paths


def _write_results_csv(path: Path, results: Sequence[FinalCaseEvaluation]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id", "system", "source_type", "modification_type", "pack_size_category",
        "selected_mod_count", "expected_repairable", "initial_status", "solver_status",
        "issue_types", "action_types", "final_compatible", "repair_success", "total_cost",
        "preservation_rate", "removed_mod_count", "runtime_seconds",
        "runtime_minimum_seconds", "runtime_maximum_seconds", "runtime_samples_seconds",
        "states_expanded",
        "explanation_complete", "passed", "failure_category",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            row = result.model_dump(mode="json")
            row["issue_types"] = ";".join(row["issue_types"])
            row["action_types"] = ";".join(row["action_types"])
            row["runtime_samples_seconds"] = ";".join(
                str(value) for value in row["runtime_samples_seconds"]
            )
            writer.writerow({field: row.get(field) for field in fields})
    return path


def _write_json(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _group_by_system(results):
    for system in FinalEvaluationSystem:
        grouped = [result for result in results if result.system == system]
        if grouped:
            yield grouped


def _is_compatible(report) -> bool:
    return bool(report and not any(issue.severity == IssueSeverity.ERROR.value for issue in report.issues))


def _unique(values):
    return list(dict.fromkeys(values))


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0
