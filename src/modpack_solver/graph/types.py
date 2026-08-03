"""Graph-specific types for dependency graph construction and inspection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import networkx as nx

from modpack_solver.models import ModpackConfig


class GraphNodeType(str, Enum):
    PROJECT = "project"
    VERSION = "version"
    MINECRAFT_VERSION = "minecraft_version"
    LOADER = "loader"


class GraphEdgeType(str, Enum):
    HAS_VERSION = "has_version"
    REQUIRES = "requires"
    OPTIONAL = "optional"
    INCOMPATIBLE = "incompatible"
    EMBEDDED = "embedded"
    SUPPORTS_MINECRAFT = "supports_minecraft"
    SUPPORTS_LOADER = "supports_loader"


@dataclass
class GraphBuildResult:
    graph: nx.DiGraph
    project_nodes: dict[str, str] = field(default_factory=dict)
    version_nodes: dict[str, str] = field(default_factory=dict)
    selected_version_nodes: dict[str, str] = field(default_factory=dict)
    unresolved_dependencies: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    config: ModpackConfig | None = None
    duplicate_selected_mod_ids: list[str] = field(default_factory=list)
