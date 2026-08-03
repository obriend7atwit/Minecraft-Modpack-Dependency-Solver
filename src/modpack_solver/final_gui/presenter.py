"""User-workflow orchestration for the final GUI and readable demo."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from modpack_solver.solver.profiles import get_weight_profile
from modpack_solver.final_dataset.cache import ModrinthCacheMode, build_case_from_modrinth_modpack
from modpack_solver.final_dataset.complexity import calculate_case_complexity
from modpack_solver.final_dataset.manifest import load_final_dataset_manifest, resolve_final_case_path
from modpack_solver.final_dataset.repair_trace import replay_repair_plan
from modpack_solver.final_dataset.sizing import classify_pack_size
from modpack_solver.final_gui.state import FinalGuiState
from modpack_solver.graph import build_graph_from_synthetic_case, summarize_graph
from modpack_solver.importers import (
    ModrinthResourceKind,
    build_case_from_project_list,
    load_case_json,
    parse_modrinth_url,
    parse_project_list,
    read_mrpack,
)
from modpack_solver.models import SyntheticCase
from modpack_solver.solver import (
    IssueSeverity,
    build_explanation_report,
    check_graph,
    format_explanation_report,
    format_issue,
    format_repair_action,
    solve_weighted_case,
)


DEFAULT_MANIFEST = Path("data/final_dataset/manifest.json")
DEFAULT_CACHE = Path("data/final_dataset/metadata_cache")


@dataclass(frozen=True)
class ResultSummary:
    """Small, user-facing view of a completed solver result."""

    status: str
    title: str
    message: str
    actions: tuple[str, ...]
    total_cost: str
    preserved: str
    removals: int
    version_changes: int


def load_json_into_state(state: FinalGuiState, path: str | Path) -> FinalGuiState:
    case = load_case_json(path)
    return _set_loaded_case(state, case, str(path), "json", Path(path).stem)


def load_builtin_sample(
    state: FinalGuiState,
    fixture_name: str,
    *,
    synthetic_dir: str | Path = "data/synthetic",
) -> FinalGuiState:
    safe_name = Path(fixture_name).name
    if safe_name != fixture_name or not safe_name.endswith(".json"):
        raise ValueError("Built-in sample must be a JSON fixture name without directories.")
    path = Path(synthetic_dir) / safe_name
    case = load_case_json(path)
    return _set_loaded_case(state, case, f"Built-in sample: {safe_name}", "built_in_sample", path.stem)


def list_builtin_samples(synthetic_dir: str | Path = "data/synthetic") -> list[str]:
    return sorted(path.name for path in Path(synthetic_dir).glob("*.json"))


def list_dataset_cases(manifest_path: str | Path = DEFAULT_MANIFEST):
    return list(load_final_dataset_manifest(manifest_path).cases)


def load_dataset_case(
    state: FinalGuiState,
    case_id: str,
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST,
) -> FinalGuiState:
    manifest = load_final_dataset_manifest(manifest_path)
    spec = next((item for item in manifest.cases if item.case_id == case_id), None)
    if spec is None:
        raise ValueError(f"Final dataset case '{case_id}' was not found.")
    case = load_case_json(resolve_final_case_path(spec, manifest_path))
    state = _set_loaded_case(
        state,
        case,
        f"Final dataset: {case_id}",
        "final_dataset",
        spec.display_name,
        dataset_spec=spec,
    )
    state.messages.append(
        f"Source={spec.source_type.value}; size={spec.pack_size_category.value}; modification={spec.modification_type.value}."
    )
    return state


def load_project_list_into_state(
    state: FinalGuiState,
    text: str,
    minecraft_version: str,
    loader: str,
    *,
    cache_dir: str | Path = DEFAULT_CACHE,
    allow_live: bool = False,
) -> FinalGuiState:
    projects = parse_project_list(text)
    case = build_case_from_project_list(
        projects,
        minecraft_version,
        loader,
        cache_dir=cache_dir,
        allow_live=allow_live,
    )
    state.metadata_mode_used = "live/cache-first" if allow_live else "offline cache"
    return _set_loaded_case(
        state,
        case,
        f"Project list: {', '.join(projects)}",
        "project_list",
        "Project list import",
    )


def load_modrinth_url_into_state(
    state: FinalGuiState,
    url: str,
    *,
    minecraft_version: str = "1.20.1",
    loader: str = "fabric",
    cache_dir: str | Path = DEFAULT_CACHE,
    allow_live: bool = False,
) -> FinalGuiState:
    parsed = parse_modrinth_url(url)
    if parsed.kind == ModrinthResourceKind.MOD:
        return load_project_list_into_state(
            state,
            parsed.slug,
            minecraft_version,
            loader,
            cache_dir=cache_dir,
            allow_live=allow_live,
        )
    mode = ModrinthCacheMode.LIVE if allow_live else ModrinthCacheMode.OFFLINE
    case = build_case_from_modrinth_modpack(
        parsed.slug,
        minecraft_version=minecraft_version or None,
        loader=loader or None,
        cache_dir=cache_dir,
        mode=mode,
    )
    state.metadata_mode_used = "live/cache-first" if allow_live else "offline normalized cache"
    return _set_loaded_case(state, case, parsed.original_url, "modrinth_url", parsed.slug)


def load_mrpack_into_state(
    state: FinalGuiState,
    path: str | Path,
    *,
    cache_dir: str | Path = DEFAULT_CACHE,
    allow_live: bool = False,
) -> FinalGuiState:
    imported = read_mrpack(path)
    if imported.loader != "fabric":
        raise ValueError(
            f"The .mrpack manifest uses loader '{imported.loader or 'unknown'}'; the current solver supports Fabric."
        )
    if not imported.minecraft_version:
        raise ValueError("The .mrpack manifest does not declare a Minecraft version.")
    if not imported.project_ids:
        raise ValueError(
            "No Modrinth project IDs could be extracted from .mrpack download URLs. "
            "The manifest was read, but metadata resolution cannot continue."
        )
    case = build_case_from_project_list(
        imported.project_ids,
        imported.minecraft_version,
        imported.loader,
        cache_dir=cache_dir,
        allow_live=allow_live,
    )
    state = _set_loaded_case(state, case, str(path), "mrpack", imported.name)
    state.messages.append(
        f"Read {len(imported.files)} manifest file entries; no downloads or installation were performed."
    )
    return state


def analyze_loaded_case(state: FinalGuiState, *, max_solutions: int = 4) -> FinalGuiState:
    if state.loaded_case is None:
        raise ValueError("Load a modpack case before running analysis.")
    state.clear_analysis()
    profile = get_weight_profile(state.selected_profile_id)
    state.progress_stage = "Building dependency graph"
    state.graph_result = build_graph_from_synthetic_case(state.loaded_case)
    state.progress_stage = "Checking compatibility"
    state.compatibility_report = check_graph(state.graph_result)
    state.progress_stage = "Running weighted solver"
    state.solver_result = solve_weighted_case(
        state.loaded_case,
        weights=profile.weights,
        max_solutions=max_solutions,
    )
    state.progress_stage = "Generating explanation"
    state.explanation_report = build_explanation_report(
        case=state.loaded_case,
        graph_result=state.graph_result,
        initial_report=state.compatibility_report,
        solver_result=state.solver_result,
    )
    state.progress_stage = "Ready"
    return state


def build_result_summary(state: FinalGuiState) -> ResultSummary:
    """Format the essential repair outcome without exposing research-only fields."""

    analyzed = _require_analysis(state)
    result = analyzed.solver_result
    original_count = len({item.mod_id for item in analyzed.loaded_case.config.selected_mods})
    actions = tuple(format_repair_action(action) for action in result.actions)
    if result.status.value == "already_compatible":
        status = "compatible"
        title = "Metadata-compatible"
        message = "No repair is needed for the available metadata."
        actions = ("Keep the current modpack selection.",)
    elif result.status.value == "solution_found":
        status = "repair_found"
        title = "Repair plan found"
        message = "Apply the recommended changes below, then re-check the pack before launching."
    else:
        status = "no_solution"
        title = "No complete repair found"
        message = (
            "The solver could not find a complete metadata-compatible plan within the available "
            "metadata and search limits. Review the advanced details for the remaining issues."
        )
        actions = actions or ("Review unresolved metadata and compatibility issues.",)
    return ResultSummary(
        status=status,
        title=title,
        message=message,
        actions=actions,
        total_cost=str(result.total_cost) if result.total_cost is not None else "N/A",
        preserved=f"{result.original_mods_preserved}/{original_count}",
        removals=result.removed_mod_count,
        version_changes=result.version_change_count,
    )


def format_modpack_summary(state: FinalGuiState) -> str:
    case = _require_case(state)
    graph = state.graph_result or build_graph_from_synthetic_case(case)
    selected = case.config.selected_mods
    unique_selected = {item.mod_id for item in selected}
    resolved = set(graph.selected_version_nodes)
    dependency_edges = Counter(
        data.get("edge_type")
        for _, _, data in graph.graph.edges(data=True)
        if data.get("edge_type") in {"requires", "optional", "incompatible", "embedded"}
    )
    top = []
    project_names = {project.mod_id: project.name for project in case.projects}
    complexity = calculate_case_complexity(case, graph)
    spec = state.loaded_dataset_spec
    for item in selected[:15]:
        top.append(f"  - {project_names.get(item.mod_id, item.mod_id)} ({item.version_number or item.version_id or 'unresolved'})")
    return "\n".join(
        [
            f"Name: {state.loaded_pack_name or 'Imported modpack'}",
            f"Source: {state.loaded_source_label or 'unknown'}",
            f"Input type: {state.loaded_input_type or 'unknown'}",
            f"Minecraft version: {case.config.minecraft_version}",
            f"Loader: {case.config.loader}",
            f"Selected entries: {len(selected)} ({len(unique_selected)} unique mods)",
            f"Pack size: {classify_pack_size(len(selected)).value}",
            f"Graph nodes/edges: {graph.graph.number_of_nodes()}/{graph.graph.number_of_edges()}",
            f"Dependency edges: {sum(dependency_edges.values())} ({_format_counts(dependency_edges)})",
            f"Metadata coverage: {len(resolved)}/{len(unique_selected)} selected mods resolved",
            f"Metadata mode: {state.metadata_mode_used}",
            "",
            "Advanced evaluation details:",
            f"  Required dependency edges: {complexity.required_edge_count}",
            f"  Required-edge density: {complexity.required_edge_density:.3f} edges per selected mod",
            f"  Maximum required-dependency depth: {complexity.maximum_required_depth}",
            f"  Mean candidate versions per mod: {complexity.mean_candidate_versions_per_mod:.2f}",
            f"  Source family: {spec.source_family_id if spec else 'not a dataset case'}",
            f"  Ground truth: {spec.ground_truth_method.value if spec else 'not applicable'}",
            f"  Original/modified: {('modified' if spec and spec.modification_type.value != 'none' else 'original/control') if spec else 'not applicable'}",
            f"  Cascading repair depth: {spec.expected_repair_action_count if spec and spec.is_cascading else 'not applicable'}",
            f"  Manifest metadata coverage: {_coverage(spec.metadata_coverage_rate) if spec else 'not applicable'}",
            "Top selected mods:",
            *(top or ["  None"]),
        ]
    )


def format_issues(state: FinalGuiState) -> str:
    report = _require_analysis(state).compatibility_report
    counts = Counter(issue.severity for issue in report.issues)
    lines = [
        f"Overall status: {report.status.value}",
        f"Errors: {counts.get('error', 0)} | Warnings: {counts.get('warning', 0)} | Info: {counts.get('info', 0)}",
        "",
    ]
    for severity in ("error", "warning", "info"):
        lines.append(severity.upper())
        matching = [issue for issue in report.issues if issue.severity == severity]
        lines.extend([f"  - {format_issue(issue)}" for issue in matching] or ["  None"])
        lines.append("")
    return "\n".join(lines).rstrip()


def format_repair_plan(state: FinalGuiState) -> str:
    analyzed = _require_analysis(state)
    result = analyzed.solver_result
    original_count = len({item.mod_id for item in analyzed.loaded_case.config.selected_mods})
    lines = [
        f"Solver status: {result.status.value}",
        f"Weight profile: {state.selected_profile_id}",
        f"Total weighted cost: {result.total_cost if result.total_cost is not None else 'N/A'}",
        f"Original mods preserved: {result.original_mods_preserved}/{original_count}",
        f"Mods removed: {result.removed_mod_count}",
        f"Version changes: {result.version_change_count}",
        f"States expanded: {result.states_expanded}",
        f"Runtime: {result.runtime_seconds * 1000:.3f} ms",
        "",
        "Selected actions:",
    ]
    lines.extend([f"  - {format_repair_action(action)}" for action in result.actions] or ["  None"])
    lines.extend(["", "Rejected alternatives:"])
    alternatives = result.alternative_solutions
    if alternatives:
        for alternative in alternatives[:3]:
            actions = ", ".join(format_repair_action(action) for action in alternative.actions) or "No actions"
            lines.append(f"  - cost {alternative.total_cost}: {actions}")
    else:
        lines.append("  None returned by the current search.")
    final_compatible = bool(
        result.final_report
        and not any(issue.severity == IssueSeverity.ERROR.value for issue in result.final_report.issues)
    )
    lines.extend(["", f"Final metadata compatibility: {'compatible' if final_compatible else 'not compatible'}"])
    return "\n".join(lines)


def format_explanation(state: FinalGuiState) -> str:
    report = _require_analysis(state).explanation_report
    return format_explanation_report(report, include_technical=True)


def format_graph_summary(state: FinalGuiState) -> str:
    analyzed = _require_analysis(state)
    complexity = calculate_case_complexity(analyzed.loaded_case, analyzed.graph_result)
    advanced = "\n".join(
        [
            "COMPLEXITY SUMMARY",
            f"Required edges: {complexity.required_edge_count}",
            f"Total dependency edges: {complexity.total_dependency_edge_count}",
            f"Required-edge density: {complexity.required_edge_density:.3f}",
            f"Maximum required depth: {complexity.maximum_required_depth}",
            f"Mean branching factor: {complexity.mean_required_branching_factor:.3f}",
            f"Connected components: {complexity.connected_component_count}",
            f"Required cycles: {complexity.required_cycle_count}",
            f"Mean candidate versions: {complexity.mean_candidate_versions_per_mod:.3f}",
            "",
        ]
    )
    return advanced + summarize_graph(analyzed.graph_result)


def format_repair_trace(state: FinalGuiState) -> str:
    analyzed = _require_analysis(state)
    actions = analyzed.solver_result.actions
    if not actions:
        return "No repair trace is needed because the solver returned no repair actions."
    trace = replay_repair_plan(analyzed.loaded_case, actions)
    lines = [
        "REPAIR TRACE",
        "",
        f"Initial status: {trace.original_report.status.value}",
    ]
    for step in trace.steps:
        before = ", ".join(item.value for item in step.issue_types_before) or "none"
        after = ", ".join(item.value for item in step.issue_types_after) or "none"
        lines.extend(
            [
                "",
                f"Step {step.step_number}: {step.action.action_type.value} {step.action.target_mod_id}",
                f"  Before: {before}",
                f"  After: {after}",
                f"  Meaning: {step.action.reason or 'Apply this repair action.'}",
            ]
        )
    lines.extend(
        [
            "",
            f"Final result: {'compatible' if trace.final_compatible else trace.final_report.status.value}",
        ]
    )
    return "\n".join(lines)


def format_dataset_summary(manifest_path: str | Path = DEFAULT_MANIFEST) -> str:
    manifest = load_final_dataset_manifest(manifest_path)
    source_counts = Counter(spec.source_type.value for spec in manifest.cases)
    size_counts = Counter(spec.pack_size_category.value for spec in manifest.cases)
    modified = sum(spec.modification_type.value != "none" for spec in manifest.cases)
    families = len({spec.source_family_id for spec in manifest.cases})
    required_edges = [spec.required_edge_count for spec in manifest.cases]
    depths = [spec.maximum_required_depth for spec in manifest.cases]
    complete_controls = sum(
        spec.source_type.value == "original_real" and bool(spec.collection_method)
        for spec in manifest.cases
    )
    complete_variants = sum(
        spec.source_type.value == "modified_real" and bool(spec.collection_method)
        for spec in manifest.cases
    )
    return "\n".join(
        [
            f"Dataset: {manifest.dataset_name} ({manifest.dataset_version})",
            f"Cases: {len(manifest.cases)}",
            f"Distinct source families: {families}",
            f"Sources: {_format_counts(source_counts)}",
            f"Sizes: {_format_counts(size_counts)}",
            f"Modified/injected cases: {modified}",
            f"Required dependency edges: {min(required_edges, default=0)} to {max(required_edges, default=0)} per case",
            f"Maximum dependency depth: {max(depths, default=0)}",
            f"Complete cached Modrinth manifests: {complete_controls} controls and {complete_variants} injected variants (manual review pending)",
            "Legacy real-data entries are reduced metadata examples; dense scale entries are controlled generated cases.",
        ]
    )


def _set_loaded_case(
    state,
    case: SyntheticCase,
    source: str,
    input_type: str,
    name: str,
    *,
    dataset_spec=None,
):
    state.loaded_case = case.model_copy(deep=True)
    state.loaded_source_label = source
    state.loaded_input_type = input_type
    state.loaded_pack_name = name
    state.loaded_dataset_spec = dataset_spec
    state.clear_analysis()
    state.progress_stage = "Ready to analyze"
    return state


def _require_case(state):
    if state.loaded_case is None:
        raise ValueError("No modpack is loaded.")
    return state.loaded_case


def _require_analysis(state):
    if not all((state.loaded_case, state.graph_result, state.compatibility_report, state.solver_result, state.explanation_report)):
        raise ValueError("Run the compatibility and weighted repair analysis first.")
    return state


def _format_counts(counter: Counter) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items())) or "none"


def _coverage(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.1%}"
