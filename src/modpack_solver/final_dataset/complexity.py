"""Deterministic graph-complexity metrics for final evaluation cases.

Dependency edges are declarations on resolved selected versions. Densities use
the number of unique selected mods as their denominator. Required depth is the
longest path through the required-edge condensation DAG, so cycles are counted
separately and cannot cause infinite traversal.
"""

from __future__ import annotations

from collections import Counter
import statistics

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.graph import GraphBuildResult, build_graph_from_synthetic_case
from modpack_solver.models import DependencyType, ModVersion, SyntheticCase


class CaseComplexityMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_mod_count: int = Field(ge=0)
    project_count: int = Field(ge=0)
    version_count: int = Field(ge=0)
    required_edge_count: int = Field(ge=0)
    optional_edge_count: int = Field(ge=0)
    incompatible_edge_count: int = Field(ge=0)
    embedded_edge_count: int = Field(ge=0)
    total_dependency_edge_count: int = Field(ge=0)
    required_edge_density: float = Field(ge=0.0)
    total_edge_density: float = Field(ge=0.0)
    maximum_required_depth: int = Field(ge=0)
    mean_required_depth: float = Field(ge=0.0)
    mean_required_branching_factor: float = Field(ge=0.0)
    maximum_required_branching_factor: int = Field(ge=0)
    connected_component_count: int = Field(ge=0)
    largest_component_mod_count: int = Field(ge=0)
    required_cycle_count: int = Field(ge=0)
    strongly_connected_component_count: int = Field(ge=0)
    mean_candidate_versions_per_mod: float = Field(ge=0.0)
    maximum_candidate_versions_per_mod: int = Field(ge=0)
    mods_with_multiple_candidate_versions: int = Field(ge=0)


def calculate_case_complexity(
    case: SyntheticCase,
    graph_result: GraphBuildResult | None = None,
) -> CaseComplexityMetrics:
    """Calculate stable structural metrics without invoking a repair solver."""

    graph_result = graph_result or build_graph_from_synthetic_case(case)
    selected_mod_ids = sorted({selected.mod_id for selected in case.config.selected_mods})
    selected_versions = _resolved_selected_versions(case, graph_result)

    edge_counts: Counter[DependencyType] = Counter()
    required_graph = nx.DiGraph()
    total_graph = nx.Graph()
    required_graph.add_nodes_from(selected_mod_ids)
    total_graph.add_nodes_from(selected_mod_ids)

    for version in selected_versions:
        for dependency in version.dependencies:
            edge_counts[dependency.dependency_type] += 1
            target = dependency.target_mod_id
            if not target:
                continue
            total_graph.add_edge(version.mod_id, target)
            if dependency.dependency_type == DependencyType.REQUIRED:
                required_graph.add_edge(version.mod_id, target)

    selected_count = len(selected_mod_ids)
    required_count = edge_counts[DependencyType.REQUIRED]
    total_count = sum(edge_counts.values())
    depths, maximum_depth = _required_depths(required_graph)
    required_outdegrees = [required_graph.out_degree(node) for node in required_graph.nodes]
    components = list(nx.connected_components(total_graph))
    strongly_connected = list(nx.strongly_connected_components(required_graph))
    cyclic_components = [
        component
        for component in strongly_connected
        if len(component) > 1
        or any(required_graph.has_edge(node, node) for node in component)
    ]

    versions_per_mod = Counter(version.mod_id for version in case.versions)
    candidate_counts = [versions_per_mod[mod_id] for mod_id in selected_mod_ids]

    return CaseComplexityMetrics(
        selected_mod_count=selected_count,
        project_count=len(case.projects),
        version_count=len(case.versions),
        required_edge_count=required_count,
        optional_edge_count=edge_counts[DependencyType.OPTIONAL],
        incompatible_edge_count=edge_counts[DependencyType.INCOMPATIBLE],
        embedded_edge_count=edge_counts[DependencyType.EMBEDDED],
        total_dependency_edge_count=total_count,
        required_edge_density=required_count / selected_count if selected_count else 0.0,
        total_edge_density=total_count / selected_count if selected_count else 0.0,
        maximum_required_depth=maximum_depth,
        mean_required_depth=statistics.fmean(depths.values()) if depths else 0.0,
        mean_required_branching_factor=(
            statistics.fmean(required_outdegrees) if required_outdegrees else 0.0
        ),
        maximum_required_branching_factor=max(required_outdegrees, default=0),
        connected_component_count=len(components),
        largest_component_mod_count=max((len(component) for component in components), default=0),
        required_cycle_count=len(cyclic_components),
        strongly_connected_component_count=len(strongly_connected),
        mean_candidate_versions_per_mod=(
            statistics.fmean(candidate_counts) if candidate_counts else 0.0
        ),
        maximum_candidate_versions_per_mod=max(candidate_counts, default=0),
        mods_with_multiple_candidate_versions=sum(count > 1 for count in candidate_counts),
    )


def _resolved_selected_versions(
    case: SyntheticCase,
    graph_result: GraphBuildResult,
) -> list[ModVersion]:
    version_map = {version.version_id: version for version in case.versions}
    resolved = []
    seen: set[str] = set()
    for node_id in graph_result.selected_version_nodes.values():
        version_id = node_id.removeprefix("version:")
        version = version_map.get(version_id)
        if version is not None and version.version_id not in seen:
            seen.add(version.version_id)
            resolved.append(version)
    return sorted(resolved, key=lambda version: (version.mod_id, version.version_id))


def _required_depths(graph: nx.DiGraph) -> tuple[dict[str, int], int]:
    if not graph:
        return {}, 0

    condensation = nx.condensation(graph)
    component_depth: dict[int, int] = {}
    for component in nx.topological_sort(condensation):
        predecessors = list(condensation.predecessors(component))
        component_depth[component] = (
            max(component_depth[parent] + 1 for parent in predecessors)
            if predecessors
            else 0
        )

    member_to_component: dict[str, int] = {}
    for component, data in condensation.nodes(data=True):
        for member in data["members"]:
            member_to_component[member] = component
    depths = {
        node: component_depth[member_to_component[node]]
        for node in graph.nodes
    }
    return depths, max(depths.values(), default=0)
