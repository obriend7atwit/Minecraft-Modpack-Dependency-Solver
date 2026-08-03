"""Week 9 experimental analysis runner."""

from __future__ import annotations

import json
import statistics
import time
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar

from modpack_solver.analysis.baseline import apply_baseline_suggestions, baseline_suggestions_for_case
from modpack_solver.analysis.failures import classify_failure
from modpack_solver.analysis.models import (
    ExperimentCaseResult,
    ExperimentSummary,
    ExperimentSystem,
    GroupMetrics,
    RuntimeMeasurements,
    SearchLimitExperimentResult,
    Week9AnalysisResult,
)
from modpack_solver.analysis.profiles import WeightProfile, get_default_profile, get_preservation_profile
from modpack_solver.evaluation import load_evaluation_manifest, run_evaluation
from modpack_solver.evaluation.metrics import preservation_rate
from modpack_solver.evaluation.models import EvaluationCaseSpec, EvaluationSourceType
from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.models import IssueType, RepairAction, RepairActionType, SyntheticCase
from modpack_solver.solver import SearchLimits, SolverResult, SolverStatus, solve_weighted_case
from modpack_solver.solver.checker import CompatibilityReport, CompatibilityStatus, IssueSeverity, check_graph


T = TypeVar("T")

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVALUATION_MANIFEST = ROOT / "data" / "evaluation" / "manifest.json"
DEFAULT_WEEK9_MANIFEST = ROOT / "data" / "experiments" / "week9_manifest.json"
DEFAULT_OUTPUT_DIR = ROOT / "results"


def measure_runtime(
    operation: Callable[[], T],
    *,
    repetitions: int = 3,
    warmup_runs: int = 1,
) -> tuple[T, RuntimeMeasurements]:
    """Measure a deterministic operation with warm-up runs excluded."""

    if repetitions < 1:
        raise ValueError("repetitions must be at least 1.")
    if warmup_runs < 0:
        raise ValueError("warmup_runs cannot be negative.")

    for _ in range(warmup_runs):
        operation()

    samples: list[float] = []
    first_result: T | None = None
    first_signature: Any = None
    for index in range(repetitions):
        started = time.perf_counter()
        result = operation()
        elapsed = time.perf_counter() - started
        samples.append(max(0.0, elapsed))
        signature = _stable_signature(result)
        if index == 0:
            first_result = result
            first_signature = signature
        elif signature != first_signature:
            raise ValueError("Repeated operation produced different deterministic outcomes.")

    assert first_result is not None
    return first_result, RuntimeMeasurements(
        samples_seconds=samples,
        median_seconds=float(statistics.median(samples)),
        minimum_seconds=min(samples),
        maximum_seconds=max(samples),
    )


def run_profile_experiment(
    manifest_path: str | Path,
    profile: WeightProfile,
    *,
    runtime_repetitions: int = 3,
    case_ids: set[str] | None = None,
) -> tuple[list[ExperimentCaseResult], ExperimentSummary]:
    specs = _filtered_specs(load_evaluation_manifest(manifest_path), case_ids)
    results = _run_profile_experiment_for_specs(specs, profile, runtime_repetitions=runtime_repetitions)
    return results, summarize_experiment_results(results)


def run_baseline_experiment(
    manifest_path: str | Path,
    *,
    runtime_repetitions: int = 3,
    case_ids: set[str] | None = None,
) -> tuple[list[ExperimentCaseResult], ExperimentSummary]:
    specs = _filtered_specs(load_evaluation_manifest(manifest_path), case_ids)
    results = _run_baseline_experiment_for_specs(specs, runtime_repetitions=runtime_repetitions)
    return results, summarize_experiment_results(results)


def run_search_limit_experiment(
    manifest_path: str | Path,
    profile: WeightProfile,
    *,
    state_limits: Sequence[int] = (5000, 10000),
    runtime_repetitions: int = 3,
) -> list[SearchLimitExperimentResult]:
    specs = load_evaluation_manifest(manifest_path)
    return _run_search_limit_experiment_for_specs(
        specs,
        profile,
        state_limits=state_limits,
        runtime_repetitions=runtime_repetitions,
    )


def run_week9_analysis(
    manifest_path: str | Path = DEFAULT_EVALUATION_MANIFEST,
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    runtime_repetitions: int = 3,
    profiles: Sequence[WeightProfile] | None = None,
    skip_baseline: bool = False,
    skip_charts: bool = False,
    case_ids: set[str] | None = None,
) -> Week9AnalysisResult:
    """Run strict validation plus Week 9 experimental comparisons."""

    manifest_path = Path(manifest_path)
    selected_profiles = list(profiles) if profiles is not None else [get_default_profile(), get_preservation_profile()]
    strict_run = run_evaluation(manifest_path, case_ids=case_ids)
    strict_validation_passed = strict_run.summary.failed_cases == 0

    main_specs = _filtered_specs(load_evaluation_manifest(manifest_path), case_ids)
    experiment_specs = _filtered_specs(_load_optional_experiment_specs(case_ids), case_ids)
    combined_specs = main_specs + experiment_specs

    case_results: list[ExperimentCaseResult] = []
    summaries: list[ExperimentSummary] = []
    if not skip_baseline:
        baseline_results = _run_baseline_experiment_for_specs(
            combined_specs,
            runtime_repetitions=runtime_repetitions,
        )
        case_results.extend(baseline_results)
        summaries.append(summarize_experiment_results(baseline_results))

    profile_result_sets: dict[str, list[ExperimentCaseResult]] = {}
    for profile in selected_profiles:
        profile_results = _run_profile_experiment_for_specs(
            combined_specs,
            profile,
            runtime_repetitions=runtime_repetitions,
        )
        profile_result_sets[profile.profile_id] = profile_results
        case_results.extend(profile_results)
        summaries.append(summarize_experiment_results(profile_results))

    search_limit_results: list[SearchLimitExperimentResult] = []
    for profile in selected_profiles:
        search_limit_results.extend(
            _run_search_limit_experiment_for_specs(
                main_specs,
                profile,
                state_limits=(5000, 10000),
                runtime_repetitions=runtime_repetitions,
            )
        )

    changed_decision_cases = _changed_decision_cases(profile_result_sets)
    result = Week9AnalysisResult(
        manifest_path=str(manifest_path),
        runtime_repetitions=runtime_repetitions,
        strict_validation_passed=strict_validation_passed,
        strict_validation_case_count=strict_run.summary.total_cases,
        case_results=case_results,
        summaries=summaries,
        search_limit_results=search_limit_results,
        changed_decision_cases=changed_decision_cases,
        solver_refinements=[
            "No algorithm changes were required because no repeated correctness problem was found."
        ],
        limitations=[
            "Cached-real cases are reduced or intentionally modified samples, not full official modpacks.",
            "The controlled trade-off case is synthetic and should not be generalized to all modpacks.",
            "Raw weighted costs from different profiles use different scales and are not directly comparable.",
            "Normal analysis is offline and does not parse full .mrpack or .jar files.",
        ],
    )

    output_path = Path(output_dir)
    _write_analysis_outputs(result, output_path, skip_charts=skip_charts)
    return result


def summarize_experiment_results(results: Sequence[ExperimentCaseResult]) -> ExperimentSummary:
    results = list(results)
    total_cases = len(results)
    system = results[0].system if results else ExperimentSystem.WEIGHTED_DEFAULT
    profile_id = results[0].profile_id if results else None
    repairable = [result for result in results if result.repair_expected]
    successful_repairs = [
        result
        for result in repairable
        if result.solution_found and result.final_compatible
    ]
    cost_values = [result.total_cost for result in successful_repairs if result.total_cost is not None]
    runtime_values = [result.runtime.median_seconds for result in results]
    suggestions = sum(result.suggestion_count for result in results)
    executable = sum(result.executable_suggestion_count for result in results)
    failure_counts = Counter(
        result.failure_category for result in results if result.failure_category
    )

    return ExperimentSummary(
        system=system,
        profile_id=profile_id,
        total_cases=total_cases,
        valid_control_cases=sum(_is_valid_control(result) for result in results),
        repairable_invalid_cases=len(repairable),
        expected_no_solution_cases=sum(result.no_solution_expected for result in results),
        successfully_repaired_cases=len(successful_repairs),
        repair_success_rate=len(successful_repairs) / len(repairable) if repairable else 0.0,
        average_repair_preservation_rate=_mean([result.preservation_rate for result in successful_repairs]),
        average_repair_action_count=_mean([result.action_count for result in successful_repairs]),
        average_repair_removed_mods=_mean([result.removed_mod_count for result in successful_repairs]),
        average_repair_cost=_mean(cost_values) if cost_values else None,
        median_runtime_seconds=float(statistics.median(runtime_values)) if runtime_values else 0.0,
        average_states_expanded=_mean([result.states_expanded for result in results]),
        issue_detection_accuracy=(
            sum(result.issue_detection_correct for result in results) / total_cases if total_cases else 0.0
        ),
        suggestion_coverage_rate=(
            sum(result.repair_expected and result.suggestion_count > 0 for result in results) / len(repairable)
            if system == ExperimentSystem.BASELINE and repairable
            else (0.0 if system == ExperimentSystem.BASELINE else None)
        ),
        executable_suggestion_rate=(
            executable / suggestions if system == ExperimentSystem.BASELINE and suggestions else
            (0.0 if system == ExperimentSystem.BASELINE else None)
        ),
        validated_baseline_repair_rate=(
            len(successful_repairs) / len(repairable)
            if system == ExperimentSystem.BASELINE and repairable
            else (0.0 if system == ExperimentSystem.BASELINE else None)
        ),
        failure_counts=dict(sorted(failure_counts.items())),
        grouped_metrics=build_grouped_metrics(results),
    )


def build_grouped_metrics(results: Sequence[ExperimentCaseResult]) -> list[GroupMetrics]:
    results = list(results)
    groups = [
        ("All cases", results),
        ("Synthetic cases", [result for result in results if result.source_type == EvaluationSourceType.SYNTHETIC]),
        (
            "Cached and modified real cases",
            [result for result in results if result.source_type != EvaluationSourceType.SYNTHETIC],
        ),
        ("Valid control cases", [result for result in results if _is_valid_control(result)]),
        ("Repairable invalid cases", [result for result in results if result.repair_expected]),
        ("Expected no-solution cases", [result for result in results if result.no_solution_expected]),
        ("Single-action repairs", [result for result in results if result.repair_expected and result.action_count == 1]),
        ("Multi-action repairs", [result for result in results if result.repair_expected and result.action_count > 1]),
    ]
    return [_group_metrics(name, group_results) for name, group_results in groups]


def _run_profile_experiment_for_specs(
    specs: Sequence[EvaluationCaseSpec],
    profile: WeightProfile,
    *,
    runtime_repetitions: int,
) -> list[ExperimentCaseResult]:
    system = (
        ExperimentSystem.WEIGHTED_PRESERVATION
        if profile.profile_id == "preservation"
        else ExperimentSystem.WEIGHTED_DEFAULT
    )
    results: list[ExperimentCaseResult] = []
    for spec in specs:
        case = load_synthetic_case(spec.fixture)
        initial_report = _initial_report(case)
        operation = lambda case=case, spec=spec, profile=profile: solve_weighted_case(
            case,
            weights=profile.weights,
            limits=spec.search_limits or SearchLimits(),
            max_solutions=4,
        )
        solver_result, runtime = measure_runtime(operation, repetitions=runtime_repetitions)
        results.append(
            _weighted_case_result(
                spec=spec,
                case=case,
                initial_report=initial_report,
                solver_result=solver_result,
                runtime=runtime,
                system=system,
                profile_id=profile.profile_id,
            )
        )
    return results


def _run_baseline_experiment_for_specs(
    specs: Sequence[EvaluationCaseSpec],
    *,
    runtime_repetitions: int,
) -> list[ExperimentCaseResult]:
    results: list[ExperimentCaseResult] = []
    for spec in specs:
        case = load_synthetic_case(spec.fixture)
        initial_report = _initial_report(case)

        def operation(case=case):
            suggestions = baseline_suggestions_for_case(case)
            return apply_baseline_suggestions(case, suggestions)

        baseline_result, runtime = measure_runtime(operation, repetitions=runtime_repetitions)
        results.append(
            _baseline_case_result(
                spec=spec,
                case=case,
                initial_report=initial_report,
                baseline_result=baseline_result,
                runtime=runtime,
            )
        )
    return results


def _run_search_limit_experiment_for_specs(
    specs: Sequence[EvaluationCaseSpec],
    profile: WeightProfile,
    *,
    state_limits: Sequence[int],
    runtime_repetitions: int,
) -> list[SearchLimitExperimentResult]:
    results: list[SearchLimitExperimentResult] = []
    for spec in specs:
        case = load_synthetic_case(spec.fixture)
        base_limits = spec.search_limits or SearchLimits()
        for max_states in state_limits:
            limits = base_limits.model_copy(update={"max_expanded_states": max_states})

            def operation(case=case, profile=profile, limits=limits):
                return solve_weighted_case(case, weights=profile.weights, limits=limits, max_solutions=4)

            solver_result, runtime = measure_runtime(operation, repetitions=runtime_repetitions)
            final_compatible = _solver_final_compatible(solver_result)
            results.append(
                SearchLimitExperimentResult(
                    case_id=spec.case_id,
                    profile_id=profile.profile_id,
                    max_expanded_states=max_states,
                    solution_found=solver_result.status == SolverStatus.SOLUTION_FOUND,
                    final_compatible=final_compatible,
                    total_cost=solver_result.total_cost,
                    states_expanded=solver_result.states_expanded,
                    runtime=runtime,
                    status=solver_result.status,
                )
            )
    return results


def _weighted_case_result(
    *,
    spec: EvaluationCaseSpec,
    case: SyntheticCase,
    initial_report: CompatibilityReport,
    solver_result: SolverResult,
    runtime: RuntimeMeasurements,
    system: ExperimentSystem,
    profile_id: str,
) -> ExperimentCaseResult:
    original_mod_count = _original_mod_count(case)
    reference_config = solver_result.repaired_config or solver_result.best_partial_config or case.config
    final_compatible = _solver_final_compatible(solver_result)
    repair_expected = spec.expected_solver_status == SolverStatus.SOLUTION_FOUND
    no_solution_expected = spec.expected_solver_status == SolverStatus.NO_SOLUTION
    result = ExperimentCaseResult(
        case_id=spec.case_id,
        name=spec.name,
        source_type=spec.source_type,
        system=system,
        profile_id=profile_id,
        original_mod_count=original_mod_count,
        initially_compatible=initial_report.status != CompatibilityStatus.INCOMPATIBLE,
        repair_expected=repair_expected,
        no_solution_expected=no_solution_expected,
        solution_found=solver_result.status == SolverStatus.SOLUTION_FOUND,
        final_compatible=final_compatible,
        issue_types=_unique_issue_types(initial_report),
        action_types=_unique_action_types(solver_result.actions),
        action_count=len(solver_result.actions),
        total_cost=solver_result.total_cost,
        original_mods_preserved=solver_result.original_mods_preserved,
        preservation_rate=preservation_rate(original_mod_count, solver_result.original_mods_preserved),
        removed_mod_count=solver_result.removed_mod_count,
        version_change_count=solver_result.version_change_count,
        states_expanded=solver_result.states_expanded,
        runtime=runtime,
        status_correct=_status_correct(spec, initial_report, solver_result.status),
        issue_detection_correct=_issue_detection_correct(spec, initial_report),
        repair_outcome_correct=_repair_outcome_correct(spec, solver_result.status, final_compatible),
    )
    category = classify_failure(spec, result, solver_result=solver_result)
    return result.model_copy(
        update={
            "failure_category": category.value if category else None,
            "failure_detail": _failure_detail(spec, result, solver_result.status),
        }
    )


def _baseline_case_result(
    *,
    spec: EvaluationCaseSpec,
    case: SyntheticCase,
    initial_report: CompatibilityReport,
    baseline_result,
    runtime: RuntimeMeasurements,
) -> ExperimentCaseResult:
    original_mod_count = _original_mod_count(case)
    repair_expected = spec.expected_solver_status == SolverStatus.SOLUTION_FOUND
    no_solution_expected = spec.expected_solver_status == SolverStatus.NO_SOLUTION
    executable_actions = baseline_result.executable_actions
    result = ExperimentCaseResult(
        case_id=spec.case_id,
        name=spec.name,
        source_type=spec.source_type,
        system=ExperimentSystem.BASELINE,
        profile_id=None,
        original_mod_count=original_mod_count,
        initially_compatible=initial_report.status != CompatibilityStatus.INCOMPATIBLE,
        repair_expected=repair_expected,
        no_solution_expected=no_solution_expected,
        suggestion_count=len(baseline_result.suggestions),
        executable_suggestion_count=len(executable_actions),
        solution_found=baseline_result.final_compatible,
        final_compatible=baseline_result.final_compatible,
        issue_types=_unique_issue_types(initial_report),
        action_types=_unique_action_types(executable_actions),
        action_count=len(executable_actions),
        total_cost=sum(action.cost for action in executable_actions) if executable_actions else 0,
        original_mods_preserved=baseline_result.original_mods_preserved,
        preservation_rate=preservation_rate(original_mod_count, baseline_result.original_mods_preserved),
        removed_mod_count=baseline_result.removed_mod_count,
        version_change_count=baseline_result.version_change_count,
        states_expanded=0,
        runtime=runtime,
        status_correct=initial_report.status == spec.expected_initial_status,
        issue_detection_correct=_issue_detection_correct(spec, initial_report),
        repair_outcome_correct=_baseline_outcome_correct(spec, baseline_result.final_compatible),
    )
    category = classify_failure(spec, result)
    return result.model_copy(
        update={
            "failure_category": category.value if category else None,
            "failure_detail": _failure_detail(spec, result, None),
        }
    )


def _initial_report(case: SyntheticCase) -> CompatibilityReport:
    return check_graph(build_graph_from_synthetic_case(case))


def _solver_final_compatible(solver_result: SolverResult) -> bool:
    return bool(
        solver_result.final_report
        and not any(issue.severity == IssueSeverity.ERROR.value for issue in solver_result.final_report.issues)
    )


def _repair_outcome_correct(
    spec: EvaluationCaseSpec,
    solver_status: SolverStatus,
    final_compatible: bool,
) -> bool:
    if spec.expected_solver_status == SolverStatus.SOLUTION_FOUND:
        return solver_status == SolverStatus.SOLUTION_FOUND and final_compatible
    if spec.expected_solver_status == SolverStatus.ALREADY_COMPATIBLE:
        return solver_status == SolverStatus.ALREADY_COMPATIBLE and final_compatible
    if spec.expected_solver_status == SolverStatus.NO_SOLUTION:
        return solver_status != SolverStatus.SOLUTION_FOUND and not final_compatible
    if spec.expected_solver_status == SolverStatus.LIMIT_REACHED:
        return solver_status == SolverStatus.LIMIT_REACHED
    if spec.expected_solver_status == SolverStatus.TIMEOUT:
        return solver_status == SolverStatus.TIMEOUT
    return True


def _baseline_outcome_correct(spec: EvaluationCaseSpec, final_compatible: bool) -> bool:
    if spec.expected_solver_status in {SolverStatus.SOLUTION_FOUND, SolverStatus.ALREADY_COMPATIBLE}:
        return final_compatible
    if spec.expected_solver_status == SolverStatus.NO_SOLUTION:
        return not final_compatible
    if spec.expected_solver_status == SolverStatus.LIMIT_REACHED:
        return not final_compatible
    return True


def _status_correct(
    spec: EvaluationCaseSpec,
    initial_report: CompatibilityReport,
    solver_status: SolverStatus,
) -> bool:
    if initial_report.status != spec.expected_initial_status:
        return False
    if spec.expected_solver_status in {SolverStatus.ALREADY_COMPATIBLE, SolverStatus.NO_SOLUTION, SolverStatus.LIMIT_REACHED}:
        return solver_status == spec.expected_solver_status
    return True


def _issue_detection_correct(spec: EvaluationCaseSpec, report: CompatibilityReport) -> bool:
    actual = set(_unique_issue_types(report))
    expected = set(spec.expected_issue_types)
    forbidden = set(spec.forbidden_issue_types)
    return expected.issubset(actual) and actual.isdisjoint(forbidden)


def _failure_detail(
    spec: EvaluationCaseSpec,
    result: ExperimentCaseResult,
    solver_status: SolverStatus | None,
) -> str | None:
    if result.status_correct and result.issue_detection_correct and result.repair_outcome_correct:
        return None
    status = solver_status.value if solver_status else "baseline"
    return (
        f"Expected initial={spec.expected_initial_status.value}, solver={spec.expected_solver_status.value}; "
        f"observed system={result.system.value}, status={status}, final_compatible={result.final_compatible}."
    )


def _group_metrics(group_name: str, results: Sequence[ExperimentCaseResult]) -> GroupMetrics:
    results = list(results)
    repairable = [result for result in results if result.repair_expected]
    successful_repairs = [
        result
        for result in repairable
        if result.solution_found and result.final_compatible
    ]
    runtimes = [result.runtime.median_seconds for result in results]
    return GroupMetrics(
        group_name=group_name,
        total_cases=len(results),
        valid_control_cases=sum(_is_valid_control(result) for result in results),
        repairable_invalid_cases=len(repairable),
        expected_no_solution_cases=sum(result.no_solution_expected for result in results),
        successfully_repaired_cases=len(successful_repairs),
        repair_success_rate=len(successful_repairs) / len(repairable) if repairable else 0.0,
        average_preservation_rate=_mean([result.preservation_rate for result in successful_repairs]),
        average_action_count=_mean([result.action_count for result in successful_repairs]),
        average_removed_mods=_mean([result.removed_mod_count for result in successful_repairs]),
        average_states_expanded=_mean([result.states_expanded for result in results]),
        median_runtime_seconds=float(statistics.median(runtimes)) if runtimes else 0.0,
        issue_detection_accuracy=(
            sum(result.issue_detection_correct for result in results) / len(results) if results else 0.0
        ),
    )


def _changed_decision_cases(profile_result_sets: dict[str, list[ExperimentCaseResult]]) -> list[str]:
    default = {result.case_id: result for result in profile_result_sets.get("default", [])}
    preservation = {result.case_id: result for result in profile_result_sets.get("preservation", [])}
    changed: list[str] = []
    for case_id in sorted(default.keys() & preservation.keys()):
        if _decision_signature(default[case_id]) != _decision_signature(preservation[case_id]):
            changed.append(case_id)
    return changed


def _decision_signature(result: ExperimentCaseResult) -> tuple:
    return (
        tuple(action_type.value for action_type in result.action_types),
        result.action_count,
        result.removed_mod_count,
        result.version_change_count,
        result.original_mods_preserved,
    )


def _load_optional_experiment_specs(case_ids: set[str] | None = None) -> list[EvaluationCaseSpec]:
    if not DEFAULT_WEEK9_MANIFEST.exists():
        return []
    return _filtered_specs(load_evaluation_manifest(DEFAULT_WEEK9_MANIFEST), case_ids)


def _filtered_specs(
    specs: Sequence[EvaluationCaseSpec],
    case_ids: set[str] | None,
) -> list[EvaluationCaseSpec]:
    if case_ids is None:
        return list(specs)
    return [spec for spec in specs if spec.case_id in case_ids]


def _write_analysis_outputs(
    result: Week9AnalysisResult,
    output_dir: Path,
    *,
    skip_charts: bool,
) -> list[Path]:
    from modpack_solver.analysis.charts import generate_all_charts
    from modpack_solver.analysis.tables import generate_analysis_tables, write_markdown_summary

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "week9_analysis.json"
    markdown_path = output_dir / "analysis_summary.md"
    generated = [json_path]
    generated.extend(generate_analysis_tables(result, output_dir))
    if not skip_charts:
        generated.extend(chart.path for chart in generate_all_charts(result, output_dir))
    generated.append(markdown_path)
    result.generated_files = [str(path) for path in generated]
    write_markdown_summary(result, markdown_path)
    _write_analysis_json(result, json_path)
    return generated


def _write_analysis_json(result: Week9AnalysisResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _unique_issue_types(report: CompatibilityReport) -> list[IssueType]:
    seen: set[IssueType] = set()
    ordered: list[IssueType] = []
    for issue in report.issues:
        if issue.issue_type in seen:
            continue
        seen.add(issue.issue_type)
        ordered.append(issue.issue_type)
    return ordered


def _unique_action_types(actions: Sequence[RepairAction]) -> list[RepairActionType]:
    seen: set[RepairActionType] = set()
    ordered: list[RepairActionType] = []
    for action in actions:
        if action.action_type in seen:
            continue
        seen.add(action.action_type)
        ordered.append(action.action_type)
    return ordered


def _original_mod_count(case: SyntheticCase) -> int:
    return len({selected.mod_id for selected in case.config.selected_mods})


def _is_valid_control(result: ExperimentCaseResult) -> bool:
    return result.initially_compatible and not result.repair_expected and not result.no_solution_expected


def _mean(values: Sequence[float | int]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return float(sum(values)) / len(values)


def _stable_signature(value: Any) -> str:
    return json.dumps(_strip_runtime(value), sort_keys=True, default=str)


def _strip_runtime(value: Any) -> Any:
    runtime_keys = {
        "runtime_seconds",
        "runtime",
        "samples_seconds",
        "median_seconds",
        "minimum_seconds",
        "maximum_seconds",
    }
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            key: _strip_runtime(item)
            for key, item in value.items()
            if key not in runtime_keys
        }
    if isinstance(value, list):
        return [_strip_runtime(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_strip_runtime(item) for item in value)
    return value
