"""Readable and structured explanation helpers for compatibility and repair results."""

from __future__ import annotations

from collections import deque

from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.graph import GraphBuildResult, GraphEdgeType, GraphNodeType, project_node_id
from modpack_solver.models import CompatibilityIssue, IssueType, RepairAction, RepairActionType, SyntheticCase
from modpack_solver.solver.checker import CompatibilityReport, IssueSeverity
from modpack_solver.solver.common import SolverResult, SolverStatus
from modpack_solver.solver.state import (
    canonical_state_key,
    count_original_mods_preserved,
    count_removed_original_mods,
    count_version_changes,
)


class ExplanationBaseModel(BaseModel):
    """Shared Pydantic configuration for explanation models."""

    model_config = ConfigDict(extra="forbid")


class IssueExplanation(ExplanationBaseModel):
    issue_type: IssueType
    severity: str
    short_summary: str
    technical_detail: str
    affected_mod_ids: list[str] = Field(default_factory=list)
    dependency_chain: list[str] = Field(default_factory=list)


class AlternativeExplanation(ExplanationBaseModel):
    actions: list[RepairAction] = Field(default_factory=list)
    total_cost: int | None = None
    accepted: bool = False
    reason: str
    original_mods_preserved: int | None = None
    removed_mod_count: int | None = None


class RepairExplanation(ExplanationBaseModel):
    selected_actions: list[RepairAction] = Field(default_factory=list)
    total_cost: int | None = None
    short_summary: str
    technical_detail: str
    original_mods_preserved: int = 0
    removed_mod_count: int = 0
    version_change_count: int = 0
    alternatives: list[AlternativeExplanation] = Field(default_factory=list)


class ExplanationReport(ExplanationBaseModel):
    overall_summary: str
    technical_summary: str
    issue_explanations: list[IssueExplanation] = Field(default_factory=list)
    repair_explanation: RepairExplanation | None = None
    baseline_suggestions: list[str] = Field(default_factory=list)
    remaining_warnings: list[str] = Field(default_factory=list)
    solver_status: str | None = None
    final_compatibility_status: str | None = None


def format_compatibility_report(report: CompatibilityReport) -> str:
    errors = [issue for issue in report.issues if issue.severity == IssueSeverity.ERROR.value]
    warnings = [issue for issue in report.issues if issue.severity == IssueSeverity.WARNING.value]
    info = [issue for issue in report.issues if issue.severity == IssueSeverity.INFO.value]

    lines = [f"Status: {report.status.value.upper()}", ""]
    lines.append("Errors:")
    lines.extend(_format_issue_section(errors))
    lines.append("")
    lines.append("Warnings:")
    lines.extend(_format_issue_section(warnings))
    lines.append("")
    lines.append("Info:")
    lines.extend(_format_issue_section(info))
    lines.append("")
    lines.append("Baseline repair suggestions:")
    if report.repair_actions:
        for action in report.repair_actions:
            lines.append(f"  - {format_repair_action(action)}")
    else:
        lines.append("  None")
    return "\n".join(lines)


def format_issue(issue: CompatibilityIssue) -> str:
    return f"[{issue.issue_type.value}] {issue.message}"


def format_repair_action(action: RepairAction) -> str:
    target_bits = [action.target_mod_id]
    if action.target_version_id:
        target_bits.append(f"version_id={action.target_version_id}")
    if action.target_version_number:
        target_bits.append(f"version={action.target_version_number}")
    target = ", ".join(target_bits)
    if action.reason:
        return f"{action.action_type.value}: {target}. {action.reason}"
    return f"{action.action_type.value}: {target}"


def explain_issue(
    issue: CompatibilityIssue,
    graph_result: GraphBuildResult | None = None,
    max_chain_depth: int = 5,
) -> IssueExplanation:
    """Build a structured short and technical explanation for one issue."""

    source_mod_id = issue.affected_mod_ids[0] if issue.affected_mod_ids else None
    target_mod_id = issue.affected_mod_ids[1] if len(issue.affected_mod_ids) > 1 else None
    source_label = _mod_label(graph_result, source_mod_id) if source_mod_id else "This mod"
    target_label = _mod_label(graph_result, target_mod_id) if target_mod_id else "the target mod"
    version_label = _selected_version_label(graph_result, source_mod_id)

    if issue.issue_type == IssueType.MISSING_DEPENDENCY:
        return IssueExplanation(
            issue_type=issue.issue_type,
            severity=issue.severity,
            short_summary=f"{target_label} is missing, so {source_label} cannot load.",
            technical_detail=(
                f"Selected mod '{source_mod_id or 'unknown'}' ({version_label or 'unresolved version'}) "
                f"has a required dependency on '{target_mod_id or 'unknown'}'. Severity={issue.severity}."
            ),
            affected_mod_ids=list(issue.affected_mod_ids),
            dependency_chain=_issue_dependency_chain(issue, graph_result, max_chain_depth),
        )

    if issue.issue_type == IssueType.MINECRAFT_VERSION_MISMATCH:
        selected_version = graph_result.config.minecraft_version if graph_result and graph_result.config else "unknown"
        supported_versions = _supported_values(graph_result, source_mod_id, "game_versions")
        return IssueExplanation(
            issue_type=issue.issue_type,
            severity=issue.severity,
            short_summary=f"This version of {source_label} does not support Minecraft {selected_version}.",
            technical_detail=(
                f"Selected mod '{source_mod_id or 'unknown'}' ({version_label or 'unresolved version'}) "
                f"does not support configured Minecraft version '{selected_version}'. "
                f"Supported versions: {', '.join(supported_versions) or 'unknown'}."
            ),
            affected_mod_ids=list(issue.affected_mod_ids),
        )

    if issue.issue_type == IssueType.LOADER_MISMATCH:
        selected_loader = graph_result.config.loader if graph_result and graph_result.config else "unknown"
        supported_loaders = _supported_values(graph_result, source_mod_id, "loaders")
        return IssueExplanation(
            issue_type=issue.issue_type,
            severity=issue.severity,
            short_summary=f"This version of {source_label} does not support the {selected_loader} loader.",
            technical_detail=(
                f"Selected mod '{source_mod_id or 'unknown'}' ({version_label or 'unresolved version'}) "
                f"does not support loader '{selected_loader}'. "
                f"Supported loaders: {', '.join(supported_loaders) or 'unknown'}."
            ),
            affected_mod_ids=list(issue.affected_mod_ids),
        )

    if issue.issue_type == IssueType.HARD_CONFLICT:
        return IssueExplanation(
            issue_type=issue.issue_type,
            severity=issue.severity,
            short_summary=f"{source_label} and {target_label} cannot be installed together.",
            technical_detail=(
                f"Selected mod '{source_mod_id or 'unknown'}' ({version_label or 'unresolved version'}) "
                f"has an incompatible relationship with '{target_mod_id or 'unknown'}'. "
                f"Severity={issue.severity}."
            ),
            affected_mod_ids=list(issue.affected_mod_ids),
            dependency_chain=_issue_dependency_chain(issue, graph_result, max_chain_depth),
        )

    if issue.issue_type == IssueType.OPTIONAL_DEPENDENCY_WARNING:
        return IssueExplanation(
            issue_type=issue.issue_type,
            severity=issue.severity,
            short_summary=f"{target_label} is optional for {source_label}, so this is a warning rather than a failure.",
            technical_detail=(
                f"Selected mod '{source_mod_id or 'unknown'}' has an optional dependency on "
                f"'{target_mod_id or 'unknown'}'. The dependency is not selected, but the checker "
                "marks it as non-fatal."
            ),
            affected_mod_ids=list(issue.affected_mod_ids),
            dependency_chain=_issue_dependency_chain(issue, graph_result, max_chain_depth),
        )

    if issue.issue_type == IssueType.DUPLICATE_MOD_VERSION:
        return IssueExplanation(
            issue_type=issue.issue_type,
            severity=issue.severity,
            short_summary=f"{source_label} was selected more than once.",
            technical_detail=(
                f"Mod '{source_mod_id or 'unknown'}' appears multiple times in the selected mod list. "
                "Only one version of a mod should remain selected in the same configuration."
            ),
            affected_mod_ids=list(issue.affected_mod_ids),
        )

    if issue.issue_type == IssueType.UNRESOLVED_SELECTED_MOD:
        return IssueExplanation(
            issue_type=issue.issue_type,
            severity=issue.severity,
            short_summary=f"{source_label} could not be matched to an available version.",
            technical_detail=(
                f"Selected mod '{source_mod_id or 'unknown'}' could not be resolved to a known version "
                "in the current metadata set, so the checker cannot validate it."
            ),
            affected_mod_ids=list(issue.affected_mod_ids),
        )

    if issue.issue_type == IssueType.UNKNOWN_DEPENDENCY_TARGET:
        return IssueExplanation(
            issue_type=issue.issue_type,
            severity=issue.severity,
            short_summary=f"{source_label} references a dependency target that is not present in available metadata.",
            technical_detail=(
                f"Selected mod '{source_mod_id or 'unknown'}' references dependency target "
                f"'{target_mod_id or 'unknown'}', but the current metadata set does not contain a "
                "matching project or version entry."
            ),
            affected_mod_ids=list(issue.affected_mod_ids),
            dependency_chain=_issue_dependency_chain(issue, graph_result, max_chain_depth),
        )

    if issue.issue_type == IssueType.EMBEDDED_DEPENDENCY_INFO:
        return IssueExplanation(
            issue_type=issue.issue_type,
            severity=issue.severity,
            short_summary=f"{target_label} is already bundled inside {source_label}.",
            technical_detail=(
                f"Selected mod '{source_mod_id or 'unknown'}' includes embedded dependency "
                f"'{target_mod_id or 'unknown'}'. The checker reports this as informational because "
                "separate installation is not required."
            ),
            affected_mod_ids=list(issue.affected_mod_ids),
            dependency_chain=_issue_dependency_chain(issue, graph_result, max_chain_depth),
        )

    return IssueExplanation(
        issue_type=issue.issue_type,
        severity=issue.severity,
        short_summary=issue.message,
        technical_detail=issue.message,
        affected_mod_ids=list(issue.affected_mod_ids),
    )


def find_dependency_chain(
    graph_result: GraphBuildResult,
    source_mod_id: str,
    target_mod_id: str,
    max_depth: int = 5,
) -> list[str]:
    """Extract a deterministic human-readable required-dependency chain."""

    graph = graph_result.graph
    start_node = graph_result.selected_version_nodes.get(source_mod_id) or graph_result.project_nodes.get(source_mod_id)
    if start_node is None:
        return []

    target_project_node = graph_result.project_nodes.get(target_mod_id, project_node_id(target_mod_id))
    target_version_node = graph_result.selected_version_nodes.get(target_mod_id)
    queue: deque[tuple[str, list[str], set[str], int]] = deque(
        [(start_node, [_chain_label(graph_result, start_node)], {start_node}, 0)]
    )

    while queue:
        node_id, label_path, seen, depth = queue.popleft()
        if depth >= max_depth:
            continue

        for next_node in _next_required_chain_nodes(graph_result, node_id):
            if next_node in seen:
                continue

            next_path = _append_label(label_path, _chain_label(graph_result, next_node))
            if next_node == target_project_node or next_node == target_version_node:
                return next_path
            if graph.nodes[next_node].get("mod_id") == target_mod_id:
                return next_path
            queue.append((next_node, next_path, seen.union({next_node}), depth + 1))

    source_label = _mod_label(graph_result, source_mod_id)
    target_label = _mod_label(graph_result, target_mod_id)
    if source_label and target_label and source_label != target_label:
        return [source_label, target_label]
    return []


def explain_solver_result(
    original_case: SyntheticCase,
    graph_result: GraphBuildResult,
    initial_report: CompatibilityReport,
    solver_result: SolverResult,
    max_alternatives: int = 3,
) -> ExplanationReport:
    """Explain a weighted solver result without rerunning the solver."""

    issue_explanations = [
        explain_issue(issue=issue, graph_result=graph_result)
        for issue in initial_report.issues
    ]
    final_report = solver_result.final_report or solver_result.best_partial_report
    remaining_warnings = []
    if final_report is not None:
        remaining_warnings = [
            format_issue(issue)
            for issue in final_report.issues
            if issue.severity in {IssueSeverity.WARNING.value, IssueSeverity.INFO.value}
        ]

    repair_explanation = _build_repair_explanation(
        original_case=original_case,
        solver_result=solver_result,
        max_alternatives=max_alternatives,
    )

    return ExplanationReport(
        overall_summary=repair_explanation.short_summary,
        technical_summary=repair_explanation.technical_detail,
        issue_explanations=issue_explanations,
        repair_explanation=repair_explanation,
        baseline_suggestions=[format_repair_action(action) for action in initial_report.repair_actions],
        remaining_warnings=remaining_warnings,
        solver_status=solver_result.status.value,
        final_compatibility_status=final_report.status.value if final_report is not None else None,
    )


def build_explanation_report(
    case: SyntheticCase,
    graph_result: GraphBuildResult,
    initial_report: CompatibilityReport,
    solver_result: SolverResult,
    max_alternatives: int = 3,
) -> ExplanationReport:
    """Public wrapper for explanation report construction."""

    return explain_solver_result(
        original_case=case,
        graph_result=graph_result,
        initial_report=initial_report,
        solver_result=solver_result,
        max_alternatives=max_alternatives,
    )


def format_explanation_report(
    report: ExplanationReport,
    *,
    include_technical: bool = True,
) -> str:
    """Format an explanation report for readable demos and GUI output."""

    lines = [
        "USER-FRIENDLY SUMMARY",
        report.overall_summary,
        "",
        "ROOT CAUSES",
    ]
    if report.issue_explanations:
        for explanation in report.issue_explanations:
            lines.append(f"  - {explanation.short_summary}")
    else:
        lines.append("  None")

    lines.extend(["", "DEPENDENCY CHAINS"])
    chain_explanations = [explanation for explanation in report.issue_explanations if explanation.dependency_chain]
    if chain_explanations:
        for explanation in chain_explanations:
            lines.append(f"  - {' -> '.join(explanation.dependency_chain)}")
    else:
        lines.append("  None")

    lines.extend(["", "SELECTED REPAIR"])
    if report.repair_explanation and report.repair_explanation.selected_actions:
        for action in report.repair_explanation.selected_actions:
            lines.append(f"  - {format_repair_action(action)}")
    else:
        lines.append("  None")
    if report.repair_explanation:
        if report.repair_explanation.total_cost is not None:
            lines.append(f"  Total cost: {report.repair_explanation.total_cost}")
        lines.append(f"  Original mods preserved: {report.repair_explanation.original_mods_preserved}")
        lines.append(f"  Removed mods: {report.repair_explanation.removed_mod_count}")
        lines.append(f"  Version changes: {report.repair_explanation.version_change_count}")

    lines.extend(["", "WHY THIS REPAIR WON"])
    if report.repair_explanation:
        lines.append(report.repair_explanation.short_summary)
    else:
        lines.append("No repair explanation is available.")

    lines.extend(["", "REJECTED ALTERNATIVES"])
    alternatives = report.repair_explanation.alternatives if report.repair_explanation else []
    if alternatives:
        for alternative in alternatives[:3]:
            action_text = ", ".join(format_repair_action(action) for action in alternative.actions) or "No actions"
            cost_text = f"cost={alternative.total_cost}" if alternative.total_cost is not None else "cost=unknown"
            lines.append(f"  - {action_text} | {cost_text}. {alternative.reason}")
    else:
        lines.append("No additional valid repair plans were returned by the current search.")

    lines.extend(["", "FINAL STATUS"])
    lines.append(f"Solver status: {report.solver_status or 'unknown'}")
    lines.append(f"Compatibility status: {report.final_compatibility_status or 'unknown'}")
    if report.remaining_warnings:
        lines.append("Remaining warnings:")
        for warning in report.remaining_warnings:
            lines.append(f"  - {warning}")
    else:
        lines.append("Remaining warnings: None")

    if include_technical:
        lines.extend(["", "TECHNICAL DETAILS", report.technical_summary])
        if report.issue_explanations:
            lines.append("")
            for explanation in report.issue_explanations:
                lines.append(f"- {explanation.issue_type.value}: {explanation.technical_detail}")
        if report.baseline_suggestions:
            lines.append("")
            lines.append("Baseline suggestions:")
            for suggestion in report.baseline_suggestions:
                lines.append(f"  - {suggestion}")

    return "\n".join(lines)


def _build_repair_explanation(
    original_case: SyntheticCase,
    solver_result: SolverResult,
    max_alternatives: int,
) -> RepairExplanation:
    original_config = original_case.config
    reference_config = solver_result.repaired_config or solver_result.best_partial_config or original_config
    original_mod_count = len({selected.mod_id for selected in original_config.selected_mods})
    preserved = count_original_mods_preserved(original_config, reference_config)
    removed = count_removed_original_mods(original_config, reference_config)
    version_changes = count_version_changes(original_config, reference_config)
    alternatives = _build_alternative_explanations(original_case, solver_result, max_alternatives)

    if solver_result.status == SolverStatus.ALREADY_COMPATIBLE:
        return RepairExplanation(
            selected_actions=[],
            total_cost=0,
            short_summary="No repair was needed because the original modpack already passed the hard compatibility checks.",
            technical_detail=(
                f"The solver returned '{solver_result.status.value}' with zero repair actions. "
                f"The original configuration preserved all {original_mod_count} selected mod(s)."
            ),
            original_mods_preserved=preserved,
            removed_mod_count=removed,
            version_change_count=version_changes,
            alternatives=alternatives,
        )

    if solver_result.status == SolverStatus.SOLUTION_FOUND:
        actions = list(solver_result.actions)
        return RepairExplanation(
            selected_actions=actions,
            total_cost=solver_result.total_cost,
            short_summary=_solution_short_summary(actions, original_case),
            technical_detail=(
                f"The solver selected {len(actions)} action(s) with weighted cost {solver_result.total_cost}. "
                f"The repaired configuration preserved {preserved} of {original_mod_count} original mod(s), "
                f"removed {removed}, changed {version_changes} version selection(s), and expanded "
                f"{solver_result.states_expanded} state(s) in {solver_result.runtime_seconds:.4f} seconds."
            ),
            original_mods_preserved=preserved,
            removed_mod_count=removed,
            version_change_count=version_changes,
            alternatives=alternatives,
        )

    if solver_result.status == SolverStatus.NO_SOLUTION:
        detail = solver_result.termination_reason or (
            "No valid repair was found using the available metadata and supported repair actions."
        )
        return RepairExplanation(
            selected_actions=[],
            total_cost=None,
            short_summary="No valid repair was found using the available metadata and supported repair actions.",
            technical_detail=(
                f"{detail} This does not prove the real-world modpack is impossible to repair; it only "
                f"describes the current metadata and action set. The best partial configuration preserved "
                f"{preserved} original mod(s) after expanding {solver_result.states_expanded} state(s)."
            ),
            original_mods_preserved=preserved,
            removed_mod_count=removed,
            version_change_count=version_changes,
            alternatives=alternatives,
        )

    if solver_result.status == SolverStatus.LIMIT_REACHED:
        detail = solver_result.termination_reason or "Search ended before all candidate repairs were explored."
        return RepairExplanation(
            selected_actions=[],
            total_cost=None,
            short_summary="The search stopped early because it hit a configured search limit, so the result is incomplete.",
            technical_detail=(
                f"{detail} The solver expanded {solver_result.states_expanded} state(s). "
                f"Runtime was {solver_result.runtime_seconds:.4f} seconds."
            ),
            original_mods_preserved=preserved,
            removed_mod_count=removed,
            version_change_count=version_changes,
            alternatives=alternatives,
        )

    detail = solver_result.termination_reason or "Search timed out before all candidate repairs were explored."
    return RepairExplanation(
        selected_actions=[],
        total_cost=None,
        short_summary="The search timed out before it could finish checking every candidate repair.",
        technical_detail=(
            f"{detail} The solver expanded {solver_result.states_expanded} state(s) in "
            f"{solver_result.runtime_seconds:.4f} seconds, so the result is incomplete."
        ),
        original_mods_preserved=preserved,
        removed_mod_count=removed,
        version_change_count=version_changes,
        alternatives=alternatives,
    )


def _build_alternative_explanations(
    original_case: SyntheticCase,
    solver_result: SolverResult,
    max_alternatives: int,
) -> list[AlternativeExplanation]:
    if solver_result.status != SolverStatus.SOLUTION_FOUND or not solver_result.alternative_solutions:
        return []

    primary_config = solver_result.repaired_config or original_case.config
    primary_cost = solver_result.total_cost or 0
    primary_preserved = count_original_mods_preserved(original_case.config, primary_config)
    primary_removed = count_removed_original_mods(original_case.config, primary_config)
    primary_action_count = len(solver_result.actions)
    primary_version_changes = count_version_changes(original_case.config, primary_config)

    alternatives: list[AlternativeExplanation] = []
    for alternative in solver_result.alternative_solutions[:max_alternatives]:
        alternative_config = alternative.repaired_config
        alternative_preserved = count_original_mods_preserved(original_case.config, alternative_config)
        alternative_removed = count_removed_original_mods(original_case.config, alternative_config)
        reason = _alternative_reason(
            primary_cost=primary_cost,
            alternative_cost=alternative.total_cost,
            primary_preserved=primary_preserved,
            alternative_preserved=alternative_preserved,
            primary_removed=primary_removed,
            alternative_removed=alternative_removed,
            primary_action_count=primary_action_count,
            alternative_action_count=len(alternative.actions),
            primary_version_changes=primary_version_changes,
            alternative_version_changes=count_version_changes(original_case.config, alternative_config),
            primary_key=canonical_state_key(primary_config),
            alternative_key=canonical_state_key(alternative_config),
        )
        alternatives.append(
            AlternativeExplanation(
                actions=list(alternative.actions),
                total_cost=alternative.total_cost,
                accepted=False,
                reason=reason,
                original_mods_preserved=alternative_preserved,
                removed_mod_count=alternative_removed,
            )
        )
    return alternatives


def _alternative_reason(
    *,
    primary_cost: int,
    alternative_cost: int,
    primary_preserved: int,
    alternative_preserved: int,
    primary_removed: int,
    alternative_removed: int,
    primary_action_count: int,
    alternative_action_count: int,
    primary_version_changes: int,
    alternative_version_changes: int,
    primary_key: tuple,
    alternative_key: tuple,
) -> str:
    if alternative_cost > primary_cost:
        return f"This repair was valid, but its weighted cost was {alternative_cost} instead of {primary_cost}."
    if alternative_preserved < primary_preserved:
        return "This repair had the same cost but preserved fewer original mods."
    if alternative_removed > primary_removed:
        return "This repair had the same cost but removed more original mods."
    if alternative_action_count > primary_action_count:
        return "This repair had the same cost and preservation rate but used more actions."
    if alternative_version_changes > primary_version_changes:
        return "This repair had the same cost and preservation rate but changed more versions."
    if alternative_key > primary_key:
        return "This repair was ranked later by deterministic tie-breaking."
    return "This repair was valid, but the current search returned another solution first."


def _issue_dependency_chain(
    issue: CompatibilityIssue,
    graph_result: GraphBuildResult | None,
    max_chain_depth: int,
) -> list[str]:
    if graph_result is None or len(issue.affected_mod_ids) < 2:
        return []

    source_mod_id = issue.affected_mod_ids[0]
    target_mod_id = issue.affected_mod_ids[1]
    best_chain: list[str] = []
    for root_mod_id in sorted(graph_result.selected_version_nodes):
        candidate = find_dependency_chain(graph_result, root_mod_id, target_mod_id, max_depth=max_chain_depth)
        if not candidate:
            continue
        if _mod_label(graph_result, source_mod_id) not in candidate and root_mod_id != source_mod_id:
            continue
        if len(candidate) > len(best_chain):
            best_chain = candidate

    if not best_chain:
        best_chain = find_dependency_chain(graph_result, source_mod_id, target_mod_id, max_depth=max_chain_depth)

    if issue.issue_type == IssueType.MISSING_DEPENDENCY and best_chain:
        best_chain = _append_label(best_chain, f"{_mod_label(graph_result, target_mod_id)} is missing")
    return best_chain


def _solution_short_summary(actions: list[RepairAction], original_case: SyntheticCase) -> str:
    if not actions:
        return "No repair action was recorded."

    first_action = actions[0]
    target_label = _case_mod_label(original_case, first_action.target_mod_id)
    if len(actions) == 1 and first_action.action_type == RepairActionType.ADD_DEPENDENCY:
        return f"The solver added {target_label} because it fixed the problem without removing any original mods."
    if len(actions) == 1 and first_action.action_type == RepairActionType.REMOVE_MOD:
        return f"The solver removed {target_label} because no cheaper valid repair was available."
    if len(actions) == 1 and first_action.action_type in {
        RepairActionType.UPGRADE_MOD,
        RepairActionType.DOWNGRADE_MOD,
        RepairActionType.UPGRADE_DEPENDENCY,
        RepairActionType.DOWNGRADE_DEPENDENCY,
    }:
        return f"The solver changed the version of {target_label} to keep the modpack compatible with minimal disruption."
    return (
        f"The solver chose a {len(actions)}-step repair plan that preserved as many original mods as possible "
        "while keeping the total weighted cost low."
    )


def _selected_version_label(graph_result: GraphBuildResult | None, mod_id: str | None) -> str | None:
    if graph_result is None or mod_id is None:
        return None
    version_node = graph_result.selected_version_nodes.get(mod_id)
    if version_node is None:
        return None
    return graph_result.graph.nodes[version_node].get("label")


def _supported_values(graph_result: GraphBuildResult | None, mod_id: str | None, key: str) -> list[str]:
    if graph_result is None or mod_id is None:
        return []
    version_node = graph_result.selected_version_nodes.get(mod_id)
    if version_node is None:
        return []
    values = graph_result.graph.nodes[version_node].get(key, [])
    return list(values) if isinstance(values, list) else []


def _mod_label(graph_result: GraphBuildResult | None, mod_id: str | None) -> str:
    if mod_id is None:
        return "unknown"
    if graph_result is None:
        return mod_id
    node_id = graph_result.project_nodes.get(mod_id, project_node_id(mod_id))
    if graph_result.graph.has_node(node_id):
        return graph_result.graph.nodes[node_id].get("label") or mod_id
    return mod_id


def _case_mod_label(case: SyntheticCase, mod_id: str) -> str:
    for project in case.projects:
        if project.mod_id == mod_id:
            return project.name
    return mod_id


def _next_required_chain_nodes(graph_result: GraphBuildResult, node_id: str) -> list[str]:
    graph = graph_result.graph
    node_type = graph.nodes[node_id].get("node_type")

    if node_type == GraphNodeType.PROJECT.value:
        mod_id = graph.nodes[node_id].get("mod_id")
        selected_version_node = graph_result.selected_version_nodes.get(mod_id)
        return [selected_version_node] if selected_version_node else []

    if node_type != GraphNodeType.VERSION.value:
        return []

    next_nodes: list[str] = []
    for _, target_node, edge_data in sorted(
        graph.out_edges(node_id, data=True),
        key=lambda item: (
            item[2].get("edge_type", ""),
            _chain_label(graph_result, item[1]),
            item[1],
        ),
    ):
        if edge_data.get("edge_type") != GraphEdgeType.REQUIRES.value:
            continue
        next_nodes.append(target_node)
        target_mod_id = graph.nodes[target_node].get("mod_id") or edge_data.get("target_mod_id")
        selected_version_node = graph_result.selected_version_nodes.get(target_mod_id) if target_mod_id else None
        if selected_version_node and selected_version_node != target_node:
            next_nodes.append(selected_version_node)
    return next_nodes


def _chain_label(graph_result: GraphBuildResult, node_id: str) -> str:
    node_data = graph_result.graph.nodes[node_id]
    if node_data.get("node_type") == GraphNodeType.VERSION.value:
        mod_id = node_data.get("mod_id")
        if mod_id:
            return _mod_label(graph_result, mod_id)
    return node_data.get("label") or node_data.get("mod_id") or node_id


def _append_label(path: list[str], label: str) -> list[str]:
    if path and path[-1] == label:
        return list(path)
    return [*path, label]


def _format_issue_section(issues: list[CompatibilityIssue]) -> list[str]:
    if not issues:
        return ["  None"]
    return [f"  - {format_issue(issue)}" for issue in issues]
