"""Dependency graph construction and summary utilities."""

from __future__ import annotations

from collections import Counter, defaultdict

import networkx as nx

from modpack_solver.graph.types import GraphBuildResult, GraphEdgeType, GraphNodeType
from modpack_solver.models import DependencyType, ModProject, ModVersion, ModpackConfig, SyntheticCase


def project_node_id(mod_id: str) -> str:
    return f"project:{mod_id}"


def version_node_id(version_id: str) -> str:
    return f"version:{version_id}"


def minecraft_node_id(minecraft_version: str) -> str:
    return f"minecraft:{minecraft_version}"


def loader_node_id(loader: str) -> str:
    return f"loader:{loader}"


def build_dependency_graph(
    config: ModpackConfig,
    projects: list[ModProject],
    versions: list[ModVersion],
) -> GraphBuildResult:
    graph = nx.DiGraph()
    result = GraphBuildResult(graph=graph, config=config)

    project_map = {project.mod_id: project for project in projects}
    version_map = {version.version_id: version for version in versions}
    versions_by_mod_id: dict[str, list[ModVersion]] = defaultdict(list)
    for version in versions:
        versions_by_mod_id[version.mod_id].append(version)

    _add_selected_context_nodes(graph, config)
    _add_project_nodes(graph, result, projects)
    _add_version_nodes(graph, result, versions, project_map)
    _add_dependency_edges(graph, result, versions, project_map, version_map)
    _resolve_selected_mods(
        graph=graph,
        result=result,
        config=config,
        version_map=version_map,
        versions_by_mod_id=versions_by_mod_id,
    )
    _add_selected_dependency_selection_warnings(
        result=result,
        config=config,
        versions=versions,
        project_map=project_map,
        version_map=version_map,
    )

    return result


def build_graph_from_synthetic_case(case: SyntheticCase) -> GraphBuildResult:
    return build_dependency_graph(
        config=case.config,
        projects=case.projects,
        versions=case.versions,
    )


def summarize_graph(result: GraphBuildResult) -> str:
    graph = result.graph
    node_type_counts = Counter(
        data.get("node_type", "unknown")
        for _, data in sorted(graph.nodes(data=True))
    )
    edge_type_counts = Counter(
        data.get("edge_type", "unknown")
        for _, _, data in sorted(graph.edges(data=True))
    )

    dependency_groups: dict[str, list[str]] = {
        GraphEdgeType.REQUIRES.value: [],
        GraphEdgeType.OPTIONAL.value: [],
        GraphEdgeType.INCOMPATIBLE.value: [],
        GraphEdgeType.EMBEDDED.value: [],
    }

    for source, target, data in sorted(graph.edges(data=True)):
        edge_type = data.get("edge_type")
        if edge_type in dependency_groups:
            dependency_groups[edge_type].append(f"{source} -> {target}")

    lines = [
        f"Nodes: {graph.number_of_nodes()}",
        f"Edges: {graph.number_of_edges()}",
        "Node counts by type:",
    ]
    for node_type in GraphNodeType:
        lines.append(f"  - {node_type.value}: {node_type_counts.get(node_type.value, 0)}")

    lines.append("Edge counts by type:")
    for edge_type in GraphEdgeType:
        lines.append(f"  - {edge_type.value}: {edge_type_counts.get(edge_type.value, 0)}")

    lines.append("Selected version nodes:")
    if result.selected_version_nodes:
        for mod_id, node_id in sorted(result.selected_version_nodes.items()):
            lines.append(f"  - {mod_id} -> {node_id}")
    else:
        lines.append("  - None")

    lines.append("Unresolved dependencies:")
    if result.unresolved_dependencies:
        for entry in sorted(result.unresolved_dependencies):
            lines.append(f"  - {entry}")
    else:
        lines.append("  - None")

    lines.append("Warnings:")
    if result.warnings:
        for warning in sorted(result.warnings):
            lines.append(f"  - {warning}")
    else:
        lines.append("  - None")

    lines.append("Dependency edges:")
    for edge_type in [
        GraphEdgeType.REQUIRES,
        GraphEdgeType.OPTIONAL,
        GraphEdgeType.INCOMPATIBLE,
        GraphEdgeType.EMBEDDED,
    ]:
        lines.append(f"  {edge_type.value.upper()}:")
        grouped_edges = dependency_groups[edge_type.value]
        if grouped_edges:
            for edge in grouped_edges:
                lines.append(f"    - {edge}")
        else:
            lines.append("    - None")

    return "\n".join(lines)


def _add_selected_context_nodes(graph: nx.DiGraph, config: ModpackConfig) -> None:
    selected_minecraft_node = minecraft_node_id(config.minecraft_version)
    graph.add_node(
        selected_minecraft_node,
        node_type=GraphNodeType.MINECRAFT_VERSION.value,
        label=config.minecraft_version,
        selected=True,
    )

    selected_loader_node = loader_node_id(config.loader)
    graph.add_node(
        selected_loader_node,
        node_type=GraphNodeType.LOADER.value,
        label=config.loader,
        selected=True,
    )


def _add_project_nodes(
    graph: nx.DiGraph,
    result: GraphBuildResult,
    projects: list[ModProject],
) -> None:
    for project in projects:
        node_id = project_node_id(project.mod_id)
        result.project_nodes[project.mod_id] = node_id
        graph.add_node(
            node_id,
            node_type=GraphNodeType.PROJECT.value,
            mod_id=project.mod_id,
            name=project.name,
            slug=project.slug,
            source=project.source.value,
            author=project.author,
            description=project.description,
            label=project.name or project.mod_id,
            selected=False,
        )


def _add_version_nodes(
    graph: nx.DiGraph,
    result: GraphBuildResult,
    versions: list[ModVersion],
    project_map: dict[str, ModProject],
) -> None:
    for version in versions:
        version_id_str = version_node_id(version.version_id)
        result.version_nodes[version.version_id] = version_id_str

        graph.add_node(
            version_id_str,
            node_type=GraphNodeType.VERSION.value,
            version_id=version.version_id,
            mod_id=version.mod_id,
            version_number=version.version_number,
            game_versions=list(version.game_versions),
            loaders=list(version.loaders),
            version_type=version.version_type,
            source=version.source.value,
            label=f"{version.mod_id}@{version.version_number}",
            selected=False,
        )

        project_id_str = project_node_id(version.mod_id)
        if version.mod_id not in project_map:
            result.warnings.append(
                f"Version '{version.version_id}' refers to unknown project '{version.mod_id}'"
            )
        else:
            graph.add_edge(
                project_id_str,
                version_id_str,
                edge_type=GraphEdgeType.HAS_VERSION.value,
            )

        for minecraft_version in version.game_versions:
            minecraft_id = minecraft_node_id(minecraft_version)
            graph.add_node(
                minecraft_id,
                node_type=GraphNodeType.MINECRAFT_VERSION.value,
                label=minecraft_version,
                selected=graph.nodes.get(minecraft_id, {}).get("selected", False),
            )
            graph.add_edge(
                version_id_str,
                minecraft_id,
                edge_type=GraphEdgeType.SUPPORTS_MINECRAFT.value,
            )

        for loader in version.loaders:
            loader_id = loader_node_id(loader)
            graph.add_node(
                loader_id,
                node_type=GraphNodeType.LOADER.value,
                label=loader,
                selected=graph.nodes.get(loader_id, {}).get("selected", False),
            )
            graph.add_edge(
                version_id_str,
                loader_id,
                edge_type=GraphEdgeType.SUPPORTS_LOADER.value,
            )


def _add_dependency_edges(
    graph: nx.DiGraph,
    result: GraphBuildResult,
    versions: list[ModVersion],
    project_map: dict[str, ModProject],
    version_map: dict[str, ModVersion],
) -> None:
    for version in versions:
        source_node = version_node_id(version.version_id)
        for dependency in version.dependencies:
            edge_type = _dependency_edge_type(dependency.dependency_type)
            target_node = _resolve_dependency_target_node(
                graph=graph,
                result=result,
                dependency=dependency,
                project_map=project_map,
                version_map=version_map,
                source_version_id=version.version_id,
            )
            graph.add_edge(
                source_node,
                target_node,
                edge_type=edge_type.value,
                dependency_type=dependency.dependency_type.value,
                target_mod_id=dependency.target_mod_id,
                target_version_id=dependency.target_version_id,
                raw_constraint=dependency.raw_constraint,
                source=dependency.source.value if dependency.source else None,
            )


def _resolve_dependency_target_node(
    graph: nx.DiGraph,
    result: GraphBuildResult,
    dependency,
    project_map: dict[str, ModProject],
    version_map: dict[str, ModVersion],
    source_version_id: str,
) -> str:
    if dependency.target_version_id and dependency.target_version_id in version_map:
        return version_node_id(dependency.target_version_id)

    if dependency.target_version_id and dependency.target_version_id not in version_map:
        unresolved = (
            f"Required dependency target version '{dependency.target_version_id}' from "
            f"'{source_version_id}' is not available in current metadata."
        )
        if dependency.dependency_type == DependencyType.REQUIRED:
            result.unresolved_dependencies.append(unresolved)
            result.warnings.append(unresolved)

    if dependency.target_mod_id and dependency.target_mod_id in project_map:
        return project_node_id(dependency.target_mod_id)

    if dependency.target_mod_id:
        target_node = project_node_id(dependency.target_mod_id)
        graph.add_node(
            target_node,
            node_type=GraphNodeType.PROJECT.value,
            mod_id=dependency.target_mod_id,
            name=None,
            slug=None,
            source=None,
            author=None,
            description=None,
            label=dependency.target_mod_id,
            selected=False,
            unresolved=True,
        )
        if dependency.dependency_type == DependencyType.REQUIRED:
            unresolved = (
                f"Required dependency target project '{dependency.target_mod_id}' from "
                f"'{source_version_id}' is not available in current metadata."
            )
            result.unresolved_dependencies.append(unresolved)
            result.warnings.append(unresolved)
        elif dependency.dependency_type == DependencyType.OPTIONAL:
            result.warnings.append(
                f"Optional dependency target project '{dependency.target_mod_id}' from "
                f"'{source_version_id}' is not available in current metadata."
            )
        return target_node

    unknown_node = project_node_id("unknown")
    graph.add_node(
        unknown_node,
        node_type=GraphNodeType.PROJECT.value,
        mod_id="unknown",
        name="unknown",
        slug=None,
        source=None,
        author=None,
        description=None,
        label="unknown",
        selected=False,
        unresolved=True,
    )
    if dependency.dependency_type == DependencyType.REQUIRED:
        unresolved = (
            f"Required dependency from '{source_version_id}' has no target project or version."
        )
        result.unresolved_dependencies.append(unresolved)
        result.warnings.append(unresolved)
    return unknown_node


def _resolve_selected_mods(
    graph: nx.DiGraph,
    result: GraphBuildResult,
    config: ModpackConfig,
    version_map: dict[str, ModVersion],
    versions_by_mod_id: dict[str, list[ModVersion]],
) -> None:
    selected_counts: dict[str, int] = defaultdict(int)
    for selected_mod in config.selected_mods:
        selected_counts[selected_mod.mod_id] += 1

    for mod_id, count in selected_counts.items():
        if count > 1:
            result.duplicate_selected_mod_ids.append(mod_id)
            result.warnings.append(
                f"Selected mod '{mod_id}' appears multiple times in the modpack selection."
            )

    for selected_mod in config.selected_mods:
        matched_version = _match_selected_mod(selected_mod, version_map, versions_by_mod_id)
        if matched_version is None:
            result.warnings.append(
                f"Selected mod '{selected_mod.mod_id}' could not be resolved to an available version"
            )
            continue

        selected_version_node = version_node_id(matched_version.version_id)
        result.selected_version_nodes[selected_mod.mod_id] = selected_version_node
        graph.nodes[selected_version_node]["selected"] = True

        project_id_str = project_node_id(selected_mod.mod_id)
        if graph.has_node(project_id_str):
            graph.nodes[project_id_str]["selected"] = True


def _match_selected_mod(selected_mod, version_map, versions_by_mod_id):
    if selected_mod.version_id:
        return version_map.get(selected_mod.version_id)

    if selected_mod.version_number:
        for version in versions_by_mod_id.get(selected_mod.mod_id, []):
            if version.version_number == selected_mod.version_number:
                return version
        return None

    available_versions = versions_by_mod_id.get(selected_mod.mod_id, [])
    if len(available_versions) == 1:
        return available_versions[0]
    return None


def _add_selected_dependency_selection_warnings(
    result: GraphBuildResult,
    config: ModpackConfig,
    versions: list[ModVersion],
    project_map: dict[str, ModProject],
    version_map: dict[str, ModVersion],
) -> None:
    selected_mod_ids = {selected_mod.mod_id for selected_mod in config.selected_mods}
    selected_version_ids = {
        node_id.removeprefix("version:") for node_id in result.selected_version_nodes.values()
    }

    for version in versions:
        if version.version_id not in selected_version_ids:
            continue

        for dependency in version.dependencies:
            if dependency.dependency_type != DependencyType.REQUIRED:
                continue

            if dependency.target_version_id:
                if dependency.target_version_id in result.version_nodes:
                    if dependency.target_version_id not in selected_version_ids:
                        result.warnings.append(
                            f"Selected version '{version.version_id}' requires version "
                            f"'{dependency.target_version_id}', but it is not currently selected."
                        )
                else:
                    continue
            elif dependency.target_mod_id in project_map:
                if dependency.target_mod_id not in selected_mod_ids:
                    result.warnings.append(
                        f"Selected version '{version.version_id}' requires project "
                        f"'{dependency.target_mod_id}', but it is not currently selected."
                    )
            elif dependency.target_mod_id or dependency.target_version_id:
                # Already handled as unresolved metadata references elsewhere.
                continue


def _dependency_edge_type(dependency_type: DependencyType) -> GraphEdgeType:
    mapping = {
        DependencyType.REQUIRED: GraphEdgeType.REQUIRES,
        DependencyType.OPTIONAL: GraphEdgeType.OPTIONAL,
        DependencyType.INCOMPATIBLE: GraphEdgeType.INCOMPATIBLE,
        DependencyType.EMBEDDED: GraphEdgeType.EMBEDDED,
    }
    return mapping[dependency_type]
