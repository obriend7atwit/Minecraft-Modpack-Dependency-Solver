"""Compatibility checking for graph-backed modpack metadata."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.graph import GraphBuildResult, GraphEdgeType, GraphNodeType, build_graph_from_synthetic_case
from modpack_solver.models import CompatibilityIssue, IssueType, RepairAction, SyntheticCase


class CompatibilityStatus(str, Enum):
    COMPATIBLE = "compatible"
    COMPATIBLE_WITH_WARNINGS = "compatible_with_warnings"
    INCOMPATIBLE = "incompatible"


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class CompatibilityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CompatibilityStatus
    issues: list[CompatibilityIssue] = Field(default_factory=list)
    repair_actions: list[RepairAction] = Field(default_factory=list)
    selected_version_nodes: dict[str, str] = Field(default_factory=dict)
    summary: str | None = None


def check_graph(result: GraphBuildResult) -> CompatibilityReport:
    """Diagnose compatibility issues from the dependency graph layer."""

    issues: list[CompatibilityIssue] = []
    issues.extend(_check_duplicate_selected_versions(result))
    issues.extend(_check_unresolved_selected_mods(result))
    issues.extend(_check_selected_versions(result))

    deduped_issues = _deduplicate_issues(issues)
    status = compute_status(deduped_issues)

    from modpack_solver.solver.baseline import suggest_baseline_repairs

    repairs = suggest_baseline_repairs(result=result, issues=deduped_issues)
    summary = _build_summary(status, deduped_issues, repairs)

    return CompatibilityReport(
        status=status,
        issues=deduped_issues,
        repair_actions=repairs,
        selected_version_nodes=dict(result.selected_version_nodes),
        summary=summary,
    )


def check_synthetic_case(case: SyntheticCase) -> CompatibilityReport:
    """Build the graph for a synthetic case and run the compatibility checker."""

    return check_graph(build_graph_from_synthetic_case(case))


def compute_status(issues: list[CompatibilityIssue]) -> CompatibilityStatus:
    if any(issue.severity == IssueSeverity.ERROR.value for issue in issues):
        return CompatibilityStatus.INCOMPATIBLE
    if any(issue.severity == IssueSeverity.WARNING.value for issue in issues):
        return CompatibilityStatus.COMPATIBLE_WITH_WARNINGS
    return CompatibilityStatus.COMPATIBLE


def _check_duplicate_selected_versions(result: GraphBuildResult) -> list[CompatibilityIssue]:
    issues: list[CompatibilityIssue] = []
    for mod_id in sorted(set(result.duplicate_selected_mod_ids)):
        issues.append(
            CompatibilityIssue(
                issue_type=IssueType.DUPLICATE_MOD_VERSION,
                message=f"Mod '{mod_id}' is selected multiple times in the modpack configuration.",
                affected_mod_ids=[mod_id],
                severity=IssueSeverity.ERROR.value,
            )
        )
    return issues


def _check_unresolved_selected_mods(result: GraphBuildResult) -> list[CompatibilityIssue]:
    issues: list[CompatibilityIssue] = []
    for warning in sorted(set(result.warnings)):
        if "could not be resolved to an available version" not in warning:
            continue
        mod_id = _extract_single_quoted_value(warning)
        issues.append(
            CompatibilityIssue(
                issue_type=IssueType.UNRESOLVED_SELECTED_MOD,
                message=warning,
                affected_mod_ids=[mod_id] if mod_id else [],
                severity=IssueSeverity.ERROR.value,
            )
        )
    return issues


def _check_selected_versions(result: GraphBuildResult) -> list[CompatibilityIssue]:
    issues: list[CompatibilityIssue] = []
    graph = result.graph
    selected_project_node_ids = {f"project:{mod_id}" for mod_id in result.selected_version_nodes}
    selected_version_node_ids = set(result.selected_version_nodes.values())
    selected_minecraft_node_id = _get_selected_context_node_id(graph, GraphNodeType.MINECRAFT_VERSION.value)
    selected_loader_node_id = _get_selected_context_node_id(graph, GraphNodeType.LOADER.value)

    for mod_id, version_node in sorted(result.selected_version_nodes.items()):
        node_data = graph.nodes[version_node]
        version_label = node_data.get("label", version_node)
        issues.extend(
            _check_required_dependencies(
                result=result,
                version_node=version_node,
                version_label=version_label,
                selected_project_node_ids=selected_project_node_ids,
                selected_version_node_ids=selected_version_node_ids,
            )
        )
        issues.extend(
            _check_optional_dependencies(
                graph=graph,
                version_node=version_node,
                version_label=version_label,
                selected_project_node_ids=selected_project_node_ids,
                selected_version_node_ids=selected_version_node_ids,
            )
        )
        issues.extend(
            _check_incompatible_dependencies(
                graph=graph,
                version_node=version_node,
                version_label=version_label,
                selected_project_node_ids=selected_project_node_ids,
                selected_version_node_ids=selected_version_node_ids,
            )
        )
        issues.extend(
            _check_embedded_dependencies(
                graph=graph,
                version_node=version_node,
                version_label=version_label,
            )
        )

        if selected_minecraft_node_id and not graph.has_edge(
            version_node, selected_minecraft_node_id
        ):
            issues.append(
                CompatibilityIssue(
                    issue_type=IssueType.MINECRAFT_VERSION_MISMATCH,
                    message=(
                        f"Selected version '{version_label}' does not support Minecraft "
                        f"'{graph.nodes[selected_minecraft_node_id].get('label')}'."
                    ),
                    affected_mod_ids=[mod_id],
                    severity=IssueSeverity.ERROR.value,
                )
            )

        if selected_loader_node_id and not graph.has_edge(version_node, selected_loader_node_id):
            issues.append(
                CompatibilityIssue(
                    issue_type=IssueType.LOADER_MISMATCH,
                    message=(
                        f"Selected version '{version_label}' does not support loader "
                        f"'{graph.nodes[selected_loader_node_id].get('label')}'."
                    ),
                    affected_mod_ids=[mod_id],
                    severity=IssueSeverity.ERROR.value,
                )
            )

    return issues


def _check_required_dependencies(
    result: GraphBuildResult,
    version_node: str,
    version_label: str,
    selected_project_node_ids: set[str],
    selected_version_node_ids: set[str],
) -> list[CompatibilityIssue]:
    issues: list[CompatibilityIssue] = []
    graph = result.graph

    for _, target_node, edge_data in sorted(graph.out_edges(version_node, data=True)):
        if edge_data.get("edge_type") != GraphEdgeType.REQUIRES.value:
            continue

        target_selected = target_node in selected_project_node_ids or target_node in selected_version_node_ids
        target_data = graph.nodes[target_node]
        target_label = target_data.get("label") or edge_data.get("target_mod_id") or edge_data.get("target_version_id") or target_node
        target_mod_id = edge_data.get("target_mod_id") or target_data.get("mod_id")
        affected_mod_ids = [mod for mod in [graph.nodes[version_node].get("mod_id"), target_mod_id] if mod]

        if target_data.get("unresolved"):
            issues.append(
                CompatibilityIssue(
                    issue_type=IssueType.UNKNOWN_DEPENDENCY_TARGET,
                    message=(
                        f"Selected version '{version_label}' has a required dependency target "
                        f"'{target_label}' that is not available in current metadata."
                    ),
                    affected_mod_ids=affected_mod_ids,
                    severity=IssueSeverity.ERROR.value,
                )
            )

        if not target_selected:
            issues.append(
                CompatibilityIssue(
                    issue_type=IssueType.MISSING_DEPENDENCY,
                    message=(
                        f"Selected version '{version_label}' requires '{target_label}', "
                        "but it is not selected."
                    ),
                    affected_mod_ids=affected_mod_ids,
                    severity=IssueSeverity.ERROR.value,
                )
            )

    return issues


def _check_optional_dependencies(
    graph,
    version_node: str,
    version_label: str,
    selected_project_node_ids: set[str],
    selected_version_node_ids: set[str],
) -> list[CompatibilityIssue]:
    issues: list[CompatibilityIssue] = []

    for _, target_node, edge_data in sorted(graph.out_edges(version_node, data=True)):
        if edge_data.get("edge_type") != GraphEdgeType.OPTIONAL.value:
            continue

        target_selected = target_node in selected_project_node_ids or target_node in selected_version_node_ids
        if target_selected:
            continue

        target_data = graph.nodes[target_node]
        target_label = target_data.get("label") or edge_data.get("target_mod_id") or target_node
        severity = (
            IssueSeverity.WARNING.value
            if not target_data.get("unresolved")
            else IssueSeverity.WARNING.value
        )
        issue_type = (
            IssueType.OPTIONAL_DEPENDENCY_WARNING
            if not target_data.get("unresolved")
            else IssueType.UNKNOWN_DEPENDENCY_TARGET
        )
        message = (
            f"Selected version '{version_label}' has optional dependency '{target_label}', "
            "which is not selected."
            if not target_data.get("unresolved")
            else (
                f"Selected version '{version_label}' has optional dependency target '{target_label}' "
                "that is not available in current metadata."
            )
        )

        affected_mod_ids = [
            mod
            for mod in [
                graph.nodes[version_node].get("mod_id"),
                edge_data.get("target_mod_id") or target_data.get("mod_id"),
            ]
            if mod
        ]
        issues.append(
            CompatibilityIssue(
                issue_type=issue_type,
                message=message,
                affected_mod_ids=affected_mod_ids,
                severity=severity,
            )
        )

    return issues


def _check_incompatible_dependencies(
    graph,
    version_node: str,
    version_label: str,
    selected_project_node_ids: set[str],
    selected_version_node_ids: set[str],
) -> list[CompatibilityIssue]:
    issues: list[CompatibilityIssue] = []

    for _, target_node, edge_data in sorted(graph.out_edges(version_node, data=True)):
        if edge_data.get("edge_type") != GraphEdgeType.INCOMPATIBLE.value:
            continue

        target_selected = target_node in selected_project_node_ids or target_node in selected_version_node_ids
        if not target_selected:
            continue

        target_data = graph.nodes[target_node]
        target_label = target_data.get("label") or edge_data.get("target_mod_id") or target_node
        affected_mod_ids = [
            mod
            for mod in [
                graph.nodes[version_node].get("mod_id"),
                edge_data.get("target_mod_id") or target_data.get("mod_id"),
            ]
            if mod
        ]

        issues.append(
            CompatibilityIssue(
                issue_type=IssueType.HARD_CONFLICT,
                message=f"Selected version '{version_label}' conflicts with selected target '{target_label}'.",
                affected_mod_ids=affected_mod_ids,
                severity=IssueSeverity.ERROR.value,
            )
        )

    return issues


def _check_embedded_dependencies(graph, version_node: str, version_label: str) -> list[CompatibilityIssue]:
    issues: list[CompatibilityIssue] = []

    for _, target_node, edge_data in sorted(graph.out_edges(version_node, data=True)):
        if edge_data.get("edge_type") != GraphEdgeType.EMBEDDED.value:
            continue

        target_data = graph.nodes[target_node]
        target_label = target_data.get("label") or edge_data.get("target_mod_id") or target_node
        issues.append(
            CompatibilityIssue(
                issue_type=IssueType.EMBEDDED_DEPENDENCY_INFO,
                message=(
                    f"Selected version '{version_label}' includes embedded dependency "
                    f"'{target_label}', which does not require a separate installation."
                ),
                affected_mod_ids=[
                    mod
                    for mod in [
                        graph.nodes[version_node].get("mod_id"),
                        edge_data.get("target_mod_id") or target_data.get("mod_id"),
                    ]
                    if mod
                ],
                severity=IssueSeverity.INFO.value,
            )
        )

    return issues


def _get_selected_context_node_id(graph, node_type: str) -> str | None:
    for node_id, data in graph.nodes(data=True):
        if data.get("node_type") == node_type and data.get("selected") is True:
            return node_id
    return None


def _extract_single_quoted_value(text: str) -> str | None:
    parts = text.split("'")
    if len(parts) >= 2:
        return parts[1]
    return None


def _deduplicate_issues(issues: list[CompatibilityIssue]) -> list[CompatibilityIssue]:
    seen: set[tuple[str, str, tuple[str, ...], str]] = set()
    deduped: list[CompatibilityIssue] = []
    for issue in issues:
        key = (
            issue.issue_type.value,
            issue.message,
            tuple(sorted(issue.affected_mod_ids)),
            issue.severity,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def _build_summary(
    status: CompatibilityStatus,
    issues: list[CompatibilityIssue],
    repair_actions: list[RepairAction],
) -> str:
    error_count = sum(issue.severity == IssueSeverity.ERROR.value for issue in issues)
    warning_count = sum(issue.severity == IssueSeverity.WARNING.value for issue in issues)
    info_count = sum(issue.severity == IssueSeverity.INFO.value for issue in issues)
    return (
        f"Status={status.value}; errors={error_count}; warnings={warning_count}; "
        f"info={info_count}; baseline_repairs={len(repair_actions)}"
    )
