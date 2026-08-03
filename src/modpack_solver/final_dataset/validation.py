"""Offline structural and behavioral validation for final dataset manifests."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from modpack_solver.final_dataset.manifest import (
    load_final_dataset_manifest,
    resolve_final_case_path,
    resolve_optional_manifest_path,
)
from modpack_solver.final_dataset.models import (
    FinalDatasetValidationResult,
    ModificationType,
)
from modpack_solver.final_dataset.complexity import calculate_case_complexity
from modpack_solver.final_dataset.sizing import classify_pack_size
from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.solver import solve_weighted_case
from modpack_solver.solver.checker import IssueSeverity, check_graph


def validate_final_dataset(
    manifest_path: str | Path,
    *,
    offline: bool = True,
    max_cases: int | None = None,
) -> FinalDatasetValidationResult:
    """Validate every selected case without requiring network access."""

    if not offline:
        raise ValueError("Final dataset validation is intentionally offline; collect metadata before validating.")
    manifest = load_final_dataset_manifest(manifest_path)
    validate_complexity_fields = manifest.dataset_version != "1.0.0"
    selected_specs = manifest.cases[:max_cases] if max_cases is not None else manifest.cases
    failures: dict[str, list[str]] = {}
    warnings: list[str] = []
    source_counts: Counter[str] = Counter()
    size_counts: Counter[str] = Counter()
    error_counts: Counter[str] = Counter()

    for spec in selected_specs:
        source_counts[spec.source_type.value] += 1
        size_counts[spec.pack_size_category.value] += 1
        errors: list[str] = []
        fixture_path = resolve_final_case_path(spec, manifest_path)
        if not fixture_path.exists():
            errors.append(f"Fixture does not exist: {fixture_path}")
            failures[spec.case_id] = errors
            continue
        if spec.cached_metadata_path:
            cache_path = resolve_optional_manifest_path(spec.cached_metadata_path, manifest_path)
            if cache_path is None or not cache_path.exists():
                errors.append(f"Cached metadata path does not exist: {cache_path}")
        if spec.modification_type != ModificationType.NONE:
            log_path = resolve_optional_manifest_path(spec.injection_log, manifest_path)
            if log_path is None or not log_path.exists():
                errors.append("Injected/modified case is missing its injection log.")

        try:
            case = load_synthetic_case(fixture_path)
            actual_count = len(case.config.selected_mods)
            if actual_count != spec.selected_mod_count:
                errors.append(
                    f"selected_mod_count is {spec.selected_mod_count}, but fixture contains {actual_count}."
                )
            if classify_pack_size(actual_count) != spec.pack_size_category:
                errors.append("Pack size category does not match the fixture's selected mod count.")
            if case.config.minecraft_version != spec.minecraft_version:
                errors.append("Manifest Minecraft version does not match fixture.")
            if case.config.loader != spec.loader:
                errors.append("Manifest loader does not match fixture.")

            graph_result = build_graph_from_synthetic_case(case)
            complexity = calculate_case_complexity(case, graph_result)
            if spec.dependency_edge_count is not None:
                dependency_edges = (
                    complexity.total_dependency_edge_count
                    if validate_complexity_fields
                    else sum(
                        data.get("edge_type")
                        in {"requires", "optional", "incompatible", "embedded"}
                        for _, _, data in graph_result.graph.edges(data=True)
                    )
                )
                if dependency_edges != spec.dependency_edge_count:
                    errors.append(
                        f"dependency_edge_count is {spec.dependency_edge_count}, observed {dependency_edges}."
                    )
            if validate_complexity_fields:
                for field_name in (
                    "project_count",
                    "version_count",
                    "required_edge_count",
                    "optional_edge_count",
                    "incompatible_edge_count",
                    "embedded_edge_count",
                    "total_dependency_edge_count",
                    "maximum_required_depth",
                    "maximum_required_branching_factor",
                    "connected_component_count",
                    "largest_component_mod_count",
                    "required_cycle_count",
                    "strongly_connected_component_count",
                    "maximum_candidate_versions_per_mod",
                    "mods_with_multiple_candidate_versions",
                ):
                    expected = getattr(spec, field_name)
                    observed = getattr(complexity, field_name)
                    if expected != observed:
                        errors.append(
                            f"{field_name} is {expected}, observed {observed}."
                        )
            report = check_graph(graph_result)
            actual_issues = {issue.issue_type for issue in report.issues}
            for issue in actual_issues:
                error_counts[issue.value] += 1
            if report.status != spec.expected_initial_status:
                errors.append(
                    f"Expected initial status {spec.expected_initial_status.value}, observed {report.status.value}."
                )
            missing_issues = set(spec.expected_issue_types) - actual_issues
            if missing_issues:
                errors.append(
                    "Missing expected issue types: " + ", ".join(sorted(issue.value for issue in missing_issues))
                )

            solver_result = solve_weighted_case(case, max_solutions=2)
            if solver_result.status != spec.expected_solver_status:
                errors.append(
                    f"Expected solver status {spec.expected_solver_status.value}, observed {solver_result.status.value}."
                )
            actual_actions = {action.action_type for action in solver_result.actions}
            missing_actions = set(spec.expected_action_types) - actual_actions
            if missing_actions:
                errors.append(
                    "Missing expected action types: " + ", ".join(sorted(action.value for action in missing_actions))
                )
            final_report = solver_result.final_report or solver_result.best_partial_report
            final_compatible = bool(
                final_report
                and not any(issue.severity == IssueSeverity.ERROR.value for issue in final_report.issues)
            )
            if final_compatible != spec.expected_final_compatible:
                errors.append(
                    f"Expected final_compatible={spec.expected_final_compatible}, observed {final_compatible}."
                )
            if spec.expected_repairable != (spec.expected_solver_status.value == "solution_found"):
                warnings.append(
                    f"Case '{spec.case_id}' expected_repairable flag differs from its expected solver status."
                )
        except Exception as exc:  # Validation must report all cases, not stop at the first one.
            errors.append(f"Validation raised {type(exc).__name__}: {exc}")

        if errors:
            failures[spec.case_id] = errors

    total = len(selected_specs)
    return FinalDatasetValidationResult(
        manifest_path=str(Path(manifest_path)),
        total_cases=total,
        passed_cases=total - len(failures),
        failed_cases=len(failures),
        warnings=warnings,
        failures=failures,
        source_type_counts=dict(sorted(source_counts.items())),
        size_category_counts=dict(sorted(size_counts.items())),
        error_type_counts=dict(sorted(error_counts.items())),
    )
