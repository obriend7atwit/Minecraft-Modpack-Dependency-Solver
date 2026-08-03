"""Deterministic dependency-topology construction helpers."""

from __future__ import annotations

from enum import Enum
import random


class DependencyTopology(str, Enum):
    CHAIN = "chain"
    BALANCED_TREE = "balanced_tree"
    LAYERED_DAG = "layered_dag"
    DIAMOND_NETWORK = "diamond_network"
    HUB_AND_SPOKE = "hub_and_spoke"
    CLUSTERED_MODULES = "clustered_modules"
    SHARED_LIBRARY_FAN_IN = "shared_library_fan_in"
    CYCLIC_REQUIRED = "cyclic_required"


def build_required_topology(
    *,
    node_count: int,
    topology: DependencyTopology,
    target_edge_count: int,
    target_depth: int,
    branching_factor: int,
    seed: int,
) -> set[tuple[int, int]]:
    """Return project-index edges with deterministic topology and bounded depth."""

    if node_count < 1:
        return set()
    topology = DependencyTopology(topology)
    depth = min(max(target_depth, 0), node_count - 1)
    branching = max(branching_factor, 1)
    levels = _assign_levels(node_count, depth, topology, branching)
    candidates = [
        (source, target)
        for source in range(node_count)
        for target in range(node_count)
        if levels[source] < levels[target]
    ]
    maximum = len(candidates)
    requested = min(max(target_edge_count, depth), maximum)

    edges = _topology_seed_edges(
        node_count=node_count,
        depth=depth,
        levels=levels,
        topology=topology,
        branching=branching,
    )
    representatives = [
        next(index for index, value in enumerate(levels) if value == level)
        for level in range(depth + 1)
    ]
    mandatory = {
        (representatives[level], representatives[level + 1])
        for level in range(depth)
    }
    if topology == DependencyTopology.CYCLIC_REQUIRED and node_count > 1:
        cycle_size = min(max(depth + 1, 2), node_count)
        mandatory.add((cycle_size - 1, 0))
        edges.add((cycle_size - 1, 0))
        requested = max(requested, len(mandatory))
    if len(edges) > requested:
        preferred_seed_edges = sorted(
            edges - mandatory,
            key=lambda edge: _edge_preference(
                edge,
                levels,
                topology,
                branching,
            ),
        )
        edges = mandatory | set(preferred_seed_edges[: max(0, requested - len(mandatory))])
    rng = random.Random(seed)
    remaining = [edge for edge in candidates if edge not in edges]
    remaining.sort(key=lambda edge: _edge_preference(edge, levels, topology, branching))
    grouped: dict[tuple, list[tuple[int, int]]] = {}
    for edge in remaining:
        key = _edge_preference(edge, levels, topology, branching)
        grouped.setdefault(key, []).append(edge)
    ordered: list[tuple[int, int]] = []
    for key in sorted(grouped):
        group = grouped[key]
        rng.shuffle(group)
        ordered.extend(group)
    for edge in ordered:
        if len(edges) >= requested:
            break
        edges.add(edge)

    return edges


def _assign_levels(
    node_count: int,
    depth: int,
    topology: DependencyTopology,
    branching: int,
) -> list[int]:
    if depth == 0:
        return [0] * node_count
    levels = [index % (depth + 1) for index in range(node_count)]
    if topology == DependencyTopology.BALANCED_TREE:
        levels = []
        for index in range(node_count):
            level = 0
            boundary = 1
            while index >= boundary and level < depth:
                level += 1
                boundary += branching ** level
            levels.append(min(level, depth))
        for level in range(depth + 1):
            if level not in levels:
                levels[level] = level
    elif topology == DependencyTopology.CLUSTERED_MODULES:
        cluster_size = max(depth + 1, 5)
        levels = [(index % cluster_size) % (depth + 1) for index in range(node_count)]
    elif topology == DependencyTopology.SHARED_LIBRARY_FAN_IN:
        levels = [
            min((index * (depth + 1)) // max(node_count, 1), depth)
            for index in range(node_count)
        ]
        for level in range(depth + 1):
            levels[level] = level
    return levels


def _topology_seed_edges(
    *,
    node_count: int,
    depth: int,
    levels: list[int],
    topology: DependencyTopology,
    branching: int,
) -> set[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    representatives = [
        next(index for index, value in enumerate(levels) if value == level)
        for level in range(depth + 1)
    ]
    edges.update(
        (representatives[level], representatives[level + 1])
        for level in range(depth)
    )

    by_level = {
        level: [index for index, value in enumerate(levels) if value == level]
        for level in range(depth + 1)
    }
    if topology in {
        DependencyTopology.CHAIN,
        DependencyTopology.CYCLIC_REQUIRED,
    }:
        for start in range(0, node_count, depth + 1):
            segment = list(range(start, min(start + depth + 1, node_count)))
            edges.update(
                (source, target)
                for source, target in zip(segment, segment[1:])
                if levels[source] < levels[target]
            )
    elif topology == DependencyTopology.BALANCED_TREE:
        for level in range(depth):
            parents = by_level[level]
            for index, child in enumerate(by_level[level + 1]):
                edges.add((parents[index % len(parents)], child))
    elif topology in {
        DependencyTopology.LAYERED_DAG,
        DependencyTopology.DIAMOND_NETWORK,
    }:
        for level in range(depth):
            targets = by_level[level + 1]
            for index, source in enumerate(by_level[level]):
                for offset in range(min(branching, len(targets))):
                    edges.add((source, targets[(index + offset) % len(targets)]))
    elif topology == DependencyTopology.HUB_AND_SPOKE:
        hub = representatives[min(1, depth)]
        edges.update(
            (source, hub)
            for source in by_level[0]
            if source != hub and levels[source] < levels[hub]
        )
    elif topology == DependencyTopology.SHARED_LIBRARY_FAN_IN:
        for level in range(depth):
            targets = by_level[level + 1][: max(1, min(branching, len(by_level[level + 1])))]
            for index, source in enumerate(by_level[level]):
                edges.add((source, targets[index % len(targets)]))
    elif topology == DependencyTopology.CLUSTERED_MODULES:
        cluster_size = max(depth + 1, 5)
        for cluster_start in range(0, node_count, cluster_size):
            cluster_end = min(cluster_start + cluster_size, node_count)
            cluster = list(range(cluster_start, cluster_end))
            for source, target in zip(cluster, cluster[1:]):
                if levels[source] < levels[target]:
                    edges.add((source, target))
        for cluster_start in range(0, node_count - cluster_size, cluster_size):
            source = min(cluster_start + depth, node_count - 1)
            target = cluster_start + cluster_size
            if levels[source] < levels[target]:
                edges.add((source, target))
    return edges


def _edge_preference(
    edge: tuple[int, int],
    levels: list[int],
    topology: DependencyTopology,
    branching: int,
) -> tuple:
    source, target = edge
    distance = levels[target] - levels[source]
    if topology == DependencyTopology.SHARED_LIBRARY_FAN_IN:
        return (target % max(branching, 1), distance, target, source)
    if topology == DependencyTopology.CLUSTERED_MODULES:
        cluster_size = max(max(levels) + 1, 5)
        return (source // cluster_size != target // cluster_size, distance, source, target)
    if topology == DependencyTopology.CHAIN:
        return (distance, abs(target - source), source, target)
    if topology == DependencyTopology.DIAMOND_NETWORK:
        return (distance, target % 2, source, target)
    return (distance, source, target)
