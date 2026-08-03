"""Build the versioned, dependency-dense offline evaluation corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from modpack_solver.final_dataset.cascading import build_cascading_cases
from modpack_solver.final_dataset.complexity import calculate_case_complexity
from modpack_solver.final_dataset.export import write_pretty_json
from modpack_solver.final_dataset.manifest import (
    load_final_dataset_manifest,
    resolve_final_case_path,
)
from modpack_solver.final_dataset.models import (
    ExpectedRepairStep,
    FinalCaseSourceType,
    FinalDatasetCaseSpec,
    FinalDatasetManifest,
    GroundTruthMethod,
    ModificationType,
)
from modpack_solver.final_dataset.reference_oracle import enumerate_reference_repairs
from modpack_solver.final_dataset.repair_trace import RepairTrace, replay_repair_plan
from modpack_solver.final_dataset.search_stress import (
    SearchStressCategory,
    build_search_stress_cases,
)
from modpack_solver.final_dataset.sizing import classify_pack_size
from modpack_solver.final_dataset.stress_generator import (
    StressCaseConfig,
    build_valid_stress_case,
    inject_missing_required_selection,
    inject_selected_version_mismatch,
)
from modpack_solver.final_dataset.topology import DependencyTopology
from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.models import RepairAction, SyntheticCase
from modpack_solver.solver.checker import IssueSeverity, check_graph
from modpack_solver.solver.common import SolverStatus
from modpack_solver.solver.costs import RepairWeights, action_cost
from modpack_solver.models import DependencyType, RepairActionType


DENSE_MATRIX = {
    "small": {"selected": 30, "edges": 45, "depth": 5, "branching": 3},
    "medium": {"selected": 80, "edges": 140, "depth": 8, "branching": 4},
    "large": {"selected": 150, "edges": 275, "depth": 12, "branching": 4},
    "huge": {"selected": 250, "edges": 475, "depth": 16, "branching": 5},
}
DENSE_TOPOLOGIES = (
    DependencyTopology.CHAIN,
    DependencyTopology.LAYERED_DAG,
    DependencyTopology.SHARED_LIBRARY_FAN_IN,
    DependencyTopology.CLUSTERED_MODULES,
)


def generate_expanded_corpus(
    *,
    output_dir: str | Path = "data/final_dataset",
    legacy_manifest_path: str | Path | None = None,
    generate_dense: bool = True,
    generate_cascading: bool = True,
    generate_search: bool = True,
) -> FinalDatasetManifest:
    """Generate v2 without using weighted solver output as expected labels."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    legacy_path = (
        Path(legacy_manifest_path)
        if legacy_manifest_path
        else output / "manifest_v1.json"
    )
    if not legacy_path.exists():
        raise FileNotFoundError(
            f"Legacy manifest '{legacy_path}' is required before generating v2."
        )
    legacy_manifest = load_final_dataset_manifest(legacy_path)
    specs = _enrich_legacy_specs(legacy_manifest.cases, legacy_path)

    if generate_dense:
        specs.extend(_write_dense_cases(output))
    if generate_cascading:
        specs.extend(_write_cascading_cases(output))
    if generate_search:
        specs.extend(_write_search_cases(output))
    specs.extend(_write_collected_real_cases(output))

    manifest = FinalDatasetManifest(
        dataset_name="Minecraft Modpack Solver Expanded Complexity Evaluation Dataset",
        dataset_version="2.0.0",
        generated_at=None,
        description=(
            "Versioned offline corpus retaining all 64 legacy cases and adding "
            "dependency-dense topology, cascading-repair, and independently "
            "enumerated search-stress cases. Analysis-ready complete Modrinth "
            "pack controls and reversible variants are included when a cached "
            "live collection is available."
        ),
        cases=specs,
    )
    write_pretty_json(output / "manifest.json", manifest)
    _write_review_queue(output, specs)
    _write_support_files(output)
    return manifest


def _enrich_legacy_specs(
    legacy_specs: Sequence[FinalDatasetCaseSpec],
    legacy_manifest_path: Path,
) -> list[FinalDatasetCaseSpec]:
    enriched = []
    for spec in legacy_specs:
        case = load_synthetic_case(resolve_final_case_path(spec, legacy_manifest_path))
        metrics = calculate_case_complexity(case)
        graph_result = build_graph_from_synthetic_case(case)
        unique_selected = {selected.mod_id for selected in case.config.selected_mods}
        resolved = set(graph_result.selected_version_nodes)
        source_family = _legacy_family(spec)
        ground_truth = (
            GroundTruthMethod.INVERSE_INJECTION
            if spec.modification_type != ModificationType.NONE
            else GroundTruthMethod.ORIGINAL_CONTROL
        )
        enriched.append(
            spec.model_copy(
                update={
                    "source_family_id": source_family,
                    "parent_case_id": spec.original_case_id,
                    "ground_truth_method": ground_truth,
                    "review_status": (
                        "validated_reduced_metadata"
                        if spec.source_type in {
                            FinalCaseSourceType.ORIGINAL_REAL,
                            FinalCaseSourceType.MODIFIED_REAL,
                        }
                        else "legacy_retained"
                    ),
                    "dependency_edge_count": metrics.total_dependency_edge_count,
                    **metrics.model_dump(exclude={"selected_mod_count"}),
                    "resolved_mod_count": len(resolved),
                    "unresolved_mod_count": max(0, len(unique_selected) - len(resolved)),
                    "metadata_coverage_rate": (
                        len(resolved) / len(unique_selected) if unique_selected else 1.0
                    ),
                    "injected_error_count": int(
                        spec.modification_type != ModificationType.NONE
                    ),
                    "expected_issue_count": len(spec.expected_issue_types),
                },
                deep=True,
            )
        )
    return enriched


def _write_dense_cases(output: Path) -> list[FinalDatasetCaseSpec]:
    fixture_dir = output / "dense_topology"
    log_dir = output / "injection_logs"
    specs: list[FinalDatasetCaseSpec] = []
    seed = 2_000
    for size_name, targets in DENSE_MATRIX.items():
        for topology in DENSE_TOPOLOGIES:
            seed += 1
            family_id = f"dense-{size_name}-{topology.value}"
            config = StressCaseConfig(
                case_id=family_id,
                selected_mod_count=targets["selected"],
                topology=topology,
                target_required_edge_count=targets["edges"],
                target_maximum_depth=targets["depth"],
                target_branching_factor=targets["branching"],
                candidate_versions_per_choice_mod=4,
                choice_mod_fraction=0.12,
                optional_edge_fraction=0.05,
                conflict_edge_count=2,
                embedded_edge_count=2,
                seed=seed,
            )
            control = build_valid_stress_case(config)
            control_id = f"{family_id}-control"
            control_path = fixture_dir / f"{control_id}.json"
            write_pretty_json(control_path, control)
            specs.append(
                _case_spec(
                    case_id=control_id,
                    display_name=f"Dense {size_name} {topology.value} control",
                    case=control,
                    fixture_path=_relative(control_path, output),
                    source_type=FinalCaseSourceType.CUSTOM_TOPOLOGY,
                    source_family_id=family_id,
                    ground_truth_method=GroundTruthMethod.ORIGINAL_CONTROL,
                    expected_solver_status=SolverStatus.ALREADY_COMPATIBLE,
                    topology=topology.value,
                    generation_config=config.model_dump(mode="json"),
                    review_status="validated",
                )
            )

            variants = [
                (
                    "missing",
                    inject_missing_required_selection(control),
                    ModificationType.REMOVE_REQUIRED_DEPENDENCY,
                ),
                (
                    "version",
                    inject_selected_version_mismatch(control),
                    ModificationType.REPLACE_WITH_INCOMPATIBLE_VERSION,
                ),
            ]
            for suffix, variant, modification in variants:
                case_id = f"{family_id}-{suffix}"
                fixture_path = fixture_dir / f"{case_id}.json"
                log_path = log_dir / f"{case_id}.json"
                write_pretty_json(fixture_path, variant.case)
                _write_injection_log(
                    log_path,
                    case_id=case_id,
                    parent_case_id=control_id,
                    description=variant.description,
                    changed_mod_ids=variant.changed_mod_ids,
                    known_repair=variant.known_valid_repair,
                )
                specs.append(
                    _case_spec(
                        case_id=case_id,
                        display_name=f"Dense {size_name} {topology.value} {suffix} injection",
                        case=variant.case,
                        fixture_path=_relative(fixture_path, output),
                        source_type=FinalCaseSourceType.CUSTOM_TOPOLOGY,
                        source_family_id=family_id,
                        parent_case_id=control_id,
                        original_case_id=control_id,
                        modification_type=modification,
                        modification_description=variant.description,
                        injection_log=_relative(log_path, output),
                        ground_truth_method=GroundTruthMethod.INVERSE_INJECTION,
                        known_valid_repair=variant.known_valid_repair,
                        expected_solver_status=SolverStatus.SOLUTION_FOUND,
                        topology=topology.value,
                        generation_config=config.model_dump(mode="json"),
                        review_status="validated",
                        injected_error_count=1,
                    )
                )
    return specs


def _write_cascading_cases(output: Path) -> list[FinalDatasetCaseSpec]:
    fixture_dir = output / "cascading_cases"
    log_dir = output / "injection_logs"
    specs = []
    for definition in build_cascading_cases():
        fixture_path = fixture_dir / f"{definition.case_id}.json"
        log_path = log_dir / f"{definition.case_id}.json"
        write_pretty_json(fixture_path, definition.case)
        _write_injection_log(
            log_path,
            case_id=definition.case_id,
            parent_case_id=None,
            description=definition.description,
            changed_mod_ids=[],
            known_repair=definition.known_valid_repair,
        )
        oracle = (
            enumerate_reference_repairs(definition.case)
            if definition.ground_truth_method == GroundTruthMethod.REFERENCE_ENUMERATION
            else None
        )
        specs.append(
            _case_spec(
                case_id=definition.case_id,
                display_name=definition.display_name,
                case=definition.case,
                fixture_path=_relative(fixture_path, output),
                source_type=FinalCaseSourceType.CASCADING_STRESS,
                source_family_id=definition.case_id,
                modification_type=(
                    ModificationType.UNSATISFIABLE
                    if definition.expected_solver_status == SolverStatus.NO_SOLUTION
                    else ModificationType.CASCADING_REPAIR
                ),
                modification_description=definition.description,
                injection_log=_relative(log_path, output),
                ground_truth_method=definition.ground_truth_method,
                known_valid_repair=definition.known_valid_repair,
                expected_solver_status=definition.expected_solver_status,
                review_status="validated_pending_manual_review",
                is_cascading=True,
                injected_error_count=max(
                    1,
                    sum(
                        issue.severity == IssueSeverity.ERROR.value
                        for issue in (
                            definition.trace.original_report.issues
                            if definition.trace
                            else check_graph(
                                build_graph_from_synthetic_case(definition.case)
                            ).issues
                        )
                    ),
                ),
                oracle=oracle,
            )
        )
    return specs


def _write_search_cases(output: Path) -> list[FinalDatasetCaseSpec]:
    fixture_dir = output / "search_stress"
    log_dir = output / "injection_logs"
    specs = []
    for definition in build_search_stress_cases():
        fixture_path = fixture_dir / f"{definition.case_id}.json"
        write_pretty_json(fixture_path, definition.case)
        oracle = enumerate_reference_repairs(definition.case)
        if not oracle.exhaustive:
            raise ValueError(f"Reference oracle did not exhaust '{definition.case_id}'.")
        modification = {
            SearchStressCategory.CANDIDATE_EXPLOSION: ModificationType.CANDIDATE_CHOICE,
            SearchStressCategory.PROFILE_SENSITIVE: ModificationType.CANDIDATE_CHOICE,
            SearchStressCategory.NO_SOLUTION: ModificationType.UNSATISFIABLE,
            SearchStressCategory.TIE_BREAKING: ModificationType.TIE_BREAKING,
        }[definition.category]
        expected_actions = (
            []
            if definition.category == SearchStressCategory.PROFILE_SENSITIVE
            else definition.known_valid_repair
        )
        log_path = log_dir / f"{definition.case_id}.json"
        description = f"Controlled {definition.category.replace('_', ' ')} search case."
        _write_injection_log(
            log_path,
            case_id=definition.case_id,
            parent_case_id=None,
            description=description,
            changed_mod_ids=[],
            known_repair=definition.known_valid_repair,
        )
        specs.append(
            _case_spec(
                case_id=definition.case_id,
                display_name=definition.display_name,
                case=definition.case,
                fixture_path=_relative(fixture_path, output),
                source_type=FinalCaseSourceType.SEARCH_STRESS,
                source_family_id=definition.case_id,
                modification_type=modification,
                modification_description=description,
                injection_log=_relative(log_path, output),
                ground_truth_method=GroundTruthMethod.REFERENCE_ENUMERATION,
                known_valid_repair=definition.known_valid_repair,
                expected_action_basis=expected_actions,
                expected_solver_status=definition.expected_solver_status,
                review_status="validated",
                injected_error_count=1,
                oracle=oracle,
                topology=definition.category,
            )
        )
    return specs


def _write_collected_real_cases(output: Path) -> list[FinalDatasetCaseSpec]:
    """Promote only checker-clean cached pack manifests into the scored corpus."""

    index_path = output / "metadata_cache" / "full_pack_collection.json"
    if not index_path.exists():
        return []
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    records = payload.get("collected", [])
    if not isinstance(records, list):
        raise ValueError("Full-pack collection index must contain a collected list.")

    specs: list[FinalDatasetCaseSpec] = []
    for raw_record in records:
        if not isinstance(raw_record, dict):
            continue
        fixture_path = Path(str(raw_record.get("normalized_case_path") or ""))
        if not fixture_path.is_absolute():
            fixture_path = Path.cwd() / fixture_path
        if not fixture_path.exists():
            continue
        try:
            fixture_relative = _relative(fixture_path, output)
        except ValueError:
            # A copied cache index must not reach outside its destination corpus.
            continue

        case = load_synthetic_case(fixture_path)
        report = check_graph(build_graph_from_synthetic_case(case))
        error_issues = [
            issue for issue in report.issues
            if issue.severity == IssueSeverity.ERROR.value
        ]
        slug = str(raw_record.get("slug") or raw_record.get("project_id") or "pack")
        version_id = str(raw_record.get("version_id") or "unknown")
        family_id = f"modrinth-full-{slug}-{version_id}"
        if error_issues:
            _write_analysis_exclusion(
                output,
                raw_record,
                error_issues=error_issues,
            )
            continue

        control_id = f"full-{_safe_case_id(slug)}-{_safe_case_id(version_id)}"
        control = _case_spec(
            case_id=control_id,
            display_name=f"{slug} complete Modrinth manifest control",
            case=case,
            fixture_path=fixture_relative,
            source_type=FinalCaseSourceType.ORIGINAL_REAL,
            source_family_id=family_id,
            ground_truth_method=GroundTruthMethod.ORIGINAL_CONTROL,
            expected_solver_status=SolverStatus.ALREADY_COMPATIBLE,
            review_status="validated_pending_manual_review",
        )
        specs.append(_with_collected_provenance(control, raw_record))

        injected = _inject_real_missing_dependency(case)
        if injected is None:
            continue
        modified_case, repair, changed_mod_ids = injected
        modified_id = f"{control_id}-missing-required"
        modified_path = output / "modified_real" / f"{modified_id}.json"
        log_path = output / "injection_logs" / f"{modified_id}.json"
        description = (
            "Removed one selected required dependency from a deep copy of the "
            "complete source manifest."
        )
        write_pretty_json(modified_path, modified_case)
        _write_injection_log(
            log_path,
            case_id=modified_id,
            parent_case_id=control_id,
            description=description,
            changed_mod_ids=changed_mod_ids,
            known_repair=[repair],
        )
        modified = _case_spec(
            case_id=modified_id,
            display_name=f"{slug} complete manifest missing-dependency injection",
            case=modified_case,
            fixture_path=_relative(modified_path, output),
            source_type=FinalCaseSourceType.MODIFIED_REAL,
            source_family_id=family_id,
            parent_case_id=control_id,
            original_case_id=control_id,
            modification_type=ModificationType.REMOVE_REQUIRED_DEPENDENCY,
            modification_description=description,
            injection_log=_relative(log_path, output),
            ground_truth_method=GroundTruthMethod.INVERSE_INJECTION,
            known_valid_repair=[repair],
            expected_solver_status=SolverStatus.SOLUTION_FOUND,
            review_status="validated_pending_manual_review",
            injected_error_count=1,
        )
        specs.append(_with_collected_provenance(modified, raw_record))
    return specs


def _inject_real_missing_dependency(
    case: SyntheticCase,
) -> tuple[SyntheticCase, RepairAction, list[str]] | None:
    """Remove a selected required target and return its exact inverse action."""

    selected_by_mod = {selected.mod_id: selected for selected in case.config.selected_mods}
    selected_versions = {}
    for selected in case.config.selected_mods:
        matches = [
            version
            for version in case.versions
            if version.mod_id == selected.mod_id
            and (
                (selected.version_id and version.version_id == selected.version_id)
                or (
                    not selected.version_id
                    and selected.version_number
                    and version.version_number == selected.version_number
                )
            )
        ]
        if len(matches) == 1:
            selected_versions[selected.mod_id] = matches[0]

    candidates = []
    for source_mod_id, version in selected_versions.items():
        for dependency in version.dependencies:
            target = selected_by_mod.get(dependency.target_mod_id)
            if dependency.dependency_type != DependencyType.REQUIRED or target is None:
                continue
            target_version = selected_versions.get(target.mod_id)
            if target_version is None:
                continue
            candidates.append((source_mod_id, target, target_version))
    if not candidates:
        return None

    source_mod_id, removed, removed_version = sorted(
        candidates,
        key=lambda item: (item[0], item[1].mod_id, item[2].version_id),
    )[0]
    modified = case.model_copy(deep=True)
    modified.config.selected_mods = [
        selected
        for selected in modified.config.selected_mods
        if selected.mod_id != removed.mod_id
    ]
    action = RepairAction(
        action_type=RepairActionType.ADD_DEPENDENCY,
        target_mod_id=removed.mod_id,
        target_version_id=removed_version.version_id,
        target_version_number=removed_version.version_number,
        reason=(
            f"Restore required dependency '{removed.mod_id}' used by "
            f"'{source_mod_id}'."
        ),
    )
    action.cost = action_cost(action, RepairWeights())
    trace = replay_repair_plan(modified, [action])
    if not trace.final_compatible:
        raise ValueError(
            f"Inverse repair for collected dependency '{removed.mod_id}' did not replay."
        )
    return modified, action, [source_mod_id, removed.mod_id]


def _with_collected_provenance(
    spec: FinalDatasetCaseSpec,
    record: dict,
) -> FinalDatasetCaseSpec:
    """Copy collection facts into a case spec without changing expected labels."""

    coverage_fields = {}
    if spec.source_type == FinalCaseSourceType.ORIGINAL_REAL:
        coverage_fields = {
            "resolved_mod_count": record.get("resolved_mod_count"),
            "unresolved_mod_count": record.get("unresolved_mod_count"),
            "metadata_coverage_rate": record.get("metadata_coverage_rate"),
        }
    return spec.model_copy(
        update={
            "source_modpack_name": record.get("slug"),
            "source_url": record.get("source_url"),
            "source_project_id": record.get("project_id"),
            "source_version_id": record.get("version_id"),
            "source_pack_slug": record.get("slug"),
            "source_pack_version_id": record.get("version_id"),
            "source_manifest_sha256": record.get("source_manifest_sha256"),
            "collected_at": record.get("collected_at"),
            "collection_method": "official_modrinth_api_mrpack_manifest_only",
            "manifest_file_count": record.get("manifest_file_count"),
            **coverage_fields,
            "license_or_terms_note": (
                "Normalized metadata only; no .mrpack archive or mod JAR is retained."
            ),
            "dataset_notes": (
                "Complete cached Modrinth pack manifest pending independent manual review."
            ),
        },
        deep=True,
    )


def _write_analysis_exclusion(
    output: Path,
    record: dict,
    *,
    error_issues,
) -> None:
    slug = str(record.get("slug") or record.get("project_id") or "pack")
    version_id = str(record.get("version_id") or "unknown")
    path = (
        output
        / "quarantine"
        / f"analysis-{_safe_case_id(slug)}-{_safe_case_id(version_id)}.json"
    )
    write_pretty_json(
        path,
        {
            "slug": slug,
            "version_id": version_id,
            "source_url": record.get("source_url"),
            "normalized_case_path": record.get("normalized_case_path"),
            "collection_status": "collected",
            "analysis_status": "excluded_pending_metadata_review",
            "reason": (
                "The normalized source manifest produces checker errors and cannot "
                "serve as an unchanged compatible control without manual adjudication."
            ),
            "checker_errors": [
                {
                    "issue_type": issue.issue_type.value,
                    "affected_mod_ids": issue.affected_mod_ids,
                    "message": issue.message,
                }
                for issue in error_issues
            ],
        },
    )


def _case_spec(
    *,
    case_id: str,
    display_name: str,
    case: SyntheticCase,
    fixture_path: str,
    source_type: FinalCaseSourceType,
    source_family_id: str,
    ground_truth_method: GroundTruthMethod,
    expected_solver_status: SolverStatus,
    review_status: str,
    known_valid_repair: Sequence[RepairAction] = (),
    expected_action_basis: Sequence[RepairAction] | None = None,
    parent_case_id: str | None = None,
    original_case_id: str | None = None,
    modification_type: ModificationType = ModificationType.NONE,
    modification_description: str | None = None,
    injection_log: str | None = None,
    topology: str | None = None,
    generation_config: dict[str, object] | None = None,
    is_cascading: bool = False,
    injected_error_count: int = 0,
    oracle=None,
) -> FinalDatasetCaseSpec:
    graph_result = build_graph_from_synthetic_case(case)
    report = check_graph(graph_result)
    metrics = calculate_case_complexity(case, graph_result)
    unique_selected = {selected.mod_id for selected in case.config.selected_mods}
    resolved = set(graph_result.selected_version_nodes)
    trace = (
        replay_repair_plan(case, known_valid_repair)
        if known_valid_repair
        else None
    )
    if trace and not trace.final_compatible:
        raise ValueError(f"Known repair for '{case_id}' did not replay successfully.")
    final_compatible = (
        trace.final_compatible
        if trace
        else not any(issue.severity == IssueSeverity.ERROR.value for issue in report.issues)
    )
    expected_issues = _stable_unique([issue.issue_type for issue in report.issues])
    action_basis = (
        list(expected_action_basis)
        if expected_action_basis is not None
        else list(known_valid_repair)
    )
    minimum_verified = bool(oracle and oracle.exhaustive)
    return FinalDatasetCaseSpec(
        case_id=case_id,
        display_name=display_name,
        source_type=source_type,
        source_family_id=source_family_id,
        parent_case_id=parent_case_id,
        original_case_id=original_case_id,
        modification_type=modification_type,
        modification_description=modification_description,
        topology=topology,
        generation_config=generation_config,
        is_cascading=is_cascading,
        injection_log=injection_log,
        fixture_path=fixture_path,
        minecraft_version=case.config.minecraft_version,
        loader=case.config.loader,
        selected_mod_count=len(case.config.selected_mods),
        dependency_edge_count=metrics.total_dependency_edge_count,
        pack_size_category=classify_pack_size(len(case.config.selected_mods)),
        resolved_mod_count=len(resolved),
        unresolved_mod_count=max(0, len(unique_selected) - len(resolved)),
        metadata_coverage_rate=(
            len(resolved) / len(unique_selected) if unique_selected else 1.0
        ),
        **metrics.model_dump(exclude={"selected_mod_count"}),
        injected_error_count=injected_error_count,
        expected_issue_count=len(expected_issues),
        expected_repair_action_count=(
            len(known_valid_repair) if known_valid_repair else None
        ),
        known_valid_repair=[
            action.model_copy(deep=True) for action in known_valid_repair
        ],
        expected_issue_trace=_expected_trace(trace),
        known_minimum_default_cost=(
            oracle.minimum_default_cost if minimum_verified else None
        ),
        known_minimum_preservation_cost=(
            oracle.minimum_preservation_cost if minimum_verified else None
        ),
        minimum_cost_verified=minimum_verified,
        expected_initial_status=report.status,
        expected_solver_status=expected_solver_status,
        expected_issue_types=expected_issues,
        expected_action_types=_stable_unique(
            [action.action_type for action in action_basis]
        ),
        expected_repairable=expected_solver_status == SolverStatus.SOLUTION_FOUND,
        expected_final_compatible=final_compatible,
        ground_truth_method=ground_truth_method,
        review_status=review_status,
        manually_reviewed=False,
        dataset_notes=(
            "Controlled generated metadata case; not an official Modrinth pack."
            if source_type
            in {
                FinalCaseSourceType.CUSTOM_TOPOLOGY,
                FinalCaseSourceType.CASCADING_STRESS,
                FinalCaseSourceType.SEARCH_STRESS,
            }
            else None
        ),
    )


def _expected_trace(trace: RepairTrace | None) -> list[ExpectedRepairStep]:
    if trace is None:
        return []
    return [
        ExpectedRepairStep(
            step_number=step.step_number,
            action_type=step.action.action_type,
            target_mod_id=step.action.target_mod_id,
            expected_issue_types_before=step.issue_types_before,
            expected_issue_types_after=step.issue_types_after,
            description=step.action.reason or "Apply the independently defined repair.",
        )
        for step in trace.steps
    ]


def _write_injection_log(
    path: Path,
    *,
    case_id: str,
    parent_case_id: str | None,
    description: str,
    changed_mod_ids: Sequence[str],
    known_repair: Sequence[RepairAction],
) -> None:
    write_pretty_json(
        path,
        {
            "case_id": case_id,
            "parent_case_id": parent_case_id,
            "description": description,
            "changed_mod_ids": list(changed_mod_ids),
            "known_inverse_repair": [
                action.model_dump(mode="json") for action in known_repair
            ],
            "ground_truth_source": "construction_or_inverse_injection",
            "observed_solver_result": None,
        },
    )


def _write_review_queue(
    output: Path,
    specs: Sequence[FinalDatasetCaseSpec],
) -> None:
    review_dir = output / "manual_review"
    review_dir.mkdir(parents=True, exist_ok=True)
    dense_sample = {
        spec.case_id
        for spec in specs
        if spec.source_type == FinalCaseSourceType.CUSTOM_TOPOLOGY
        and spec.case_id.endswith("-control")
    }
    selected = [
        spec
        for spec in specs
        if spec.source_type
        in {
            FinalCaseSourceType.ORIGINAL_REAL,
            FinalCaseSourceType.MODIFIED_REAL,
            FinalCaseSourceType.EXISTING_BROKEN,
            FinalCaseSourceType.CASCADING_STRESS,
        }
        or spec.expected_solver_status == SolverStatus.NO_SOLUTION
        or spec.case_id in dense_sample
    ]
    for spec in selected:
        path = review_dir / f"{spec.case_id}.json"
        if path.exists():
            continue
        write_pretty_json(
            path,
            {
                "case_id": spec.case_id,
                "reviewer": None,
                "reviewed_at": None,
                "source_provenance_valid": None,
                "injection_matches_description": None,
                "expected_issue_correct": None,
                "known_repair_valid": None,
                "solver_result_reasonable": None,
                "explanation_understandable": None,
                "notes": "",
            },
        )


def _write_support_files(output: Path) -> None:
    for directory in ("existing_broken", "quarantine"):
        (output / directory).mkdir(parents=True, exist_ok=True)
    broken_sources = output / "broken_sources.json"
    if not broken_sources.exists():
        write_pretty_json(
            broken_sources,
            {
                "sources": [],
                "note": (
                    "No naturally broken public example has yet met the documented "
                    "reproduction and manual-review criteria."
                ),
            },
        )


def _legacy_family(spec: FinalDatasetCaseSpec) -> str:
    if spec.original_case_id:
        return spec.original_case_id
    if spec.case_id.startswith("custom-"):
        parts = spec.case_id.split("-")
        if len(parts) >= 3 and parts[1] in {"small", "medium", "large", "huge"}:
            return f"legacy-custom-{parts[1]}"
    return spec.case_id


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _safe_case_id(value: str) -> str:
    return "".join(
        character.lower() if character.isalnum() else "-"
        for character in value
    ).strip("-")


def _stable_unique(values):
    seen = set()
    ordered = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
