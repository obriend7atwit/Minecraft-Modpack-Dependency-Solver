"""Shared models and helpers for weighted solver workflows."""

from __future__ import annotations

from enum import Enum
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.graph import build_dependency_graph
from modpack_solver.models import ModpackConfig, ModProject, ModVersion, RepairAction
from modpack_solver.solver.checker import CompatibilityReport, IssueSeverity, check_graph
from modpack_solver.versioning import version_sort_key


class SearchLimits(BaseModel):
    """Safety limits for the first weighted-search implementation."""

    model_config = ConfigDict(extra="forbid")

    max_repair_actions: int = Field(default=6, ge=0)
    max_expanded_states: int = Field(default=5000, ge=1)
    timeout_seconds: float = Field(default=10.0, gt=0)


class SolverStatus(str, Enum):
    ALREADY_COMPATIBLE = "already_compatible"
    SOLUTION_FOUND = "solution_found"
    NO_SOLUTION = "no_solution"
    LIMIT_REACHED = "limit_reached"
    TIMEOUT = "timeout"


class SolverSolution(BaseModel):
    """A single validated weighted-solver repair candidate."""

    model_config = ConfigDict(extra="forbid")

    repaired_config: ModpackConfig
    actions: list[RepairAction] = Field(default_factory=list)
    total_cost: int = 0
    final_report: CompatibilityReport


class SolverResult(BaseModel):
    """Structured weighted-solver output for success and failure paths."""

    model_config = ConfigDict(extra="forbid")

    status: SolverStatus
    original_config: ModpackConfig
    repaired_config: ModpackConfig | None = None
    actions: list[RepairAction] = Field(default_factory=list)
    total_cost: int | None = None
    final_report: CompatibilityReport | None = None
    states_expanded: int = 0
    runtime_seconds: float = 0.0
    limit_reached: bool = False
    best_partial_config: ModpackConfig | None = None
    best_partial_report: CompatibilityReport | None = None
    alternative_solutions: list[SolverSolution] = Field(default_factory=list)
    solutions_found: int = 0
    termination_reason: str | None = None
    candidate_actions_generated: int = 0
    original_mods_preserved: int = 0
    removed_mod_count: int = 0
    version_change_count: int = 0


class SolverComparison(BaseModel):
    """Lightweight baseline-versus-weighted comparison summary."""

    model_config = ConfigDict(extra="forbid")

    baseline_actions: list[RepairAction] = Field(default_factory=list)
    baseline_action_count: int = 0
    baseline_estimated_cost: int | None = None
    weighted_status: SolverStatus
    weighted_actions: list[RepairAction] = Field(default_factory=list)
    weighted_action_count: int = 0
    weighted_cost: int | None = None
    original_mods_preserved: int = 0
    removed_mods: int = 0
    runtime_seconds: float = 0.0


def evaluate_config(
    config: ModpackConfig,
    projects: Sequence[ModProject],
    versions: Sequence[ModVersion],
) -> CompatibilityReport:
    """Evaluate a candidate configuration through the existing graph/checker pipeline."""

    graph_result = build_dependency_graph(
        config=config.model_copy(deep=True),
        projects=[project.model_copy(deep=True) for project in projects],
        versions=[version.model_copy(deep=True) for version in versions],
    )
    return check_graph(graph_result)


def versions_for_mod(mod_id: str, versions: Sequence[ModVersion]) -> list[ModVersion]:
    """Return all known versions for one mod in deterministic order."""

    matching = [version for version in versions if version.mod_id == mod_id]
    return sorted(
        matching,
        key=lambda version: (version_sort_key(version.version_number), version.version_id),
    )


def compatible_versions_for_mod(
    mod_id: str,
    config: ModpackConfig,
    versions: Sequence[ModVersion],
) -> list[ModVersion]:
    """Return versions for a mod that match the current Minecraft version and loader."""

    compatible: list[ModVersion] = []
    for version in versions_for_mod(mod_id, versions):
        if config.minecraft_version not in version.game_versions:
            continue
        if config.loader not in version.loaders:
            continue
        compatible.append(version)
    return compatible


def resolve_selected_versions(
    config: ModpackConfig,
    versions: Sequence[ModVersion],
) -> dict[str, ModVersion]:
    """Resolve selected mods to concrete version objects using current metadata."""

    version_map = {version.version_id: version for version in versions}
    versions_by_mod_id: dict[str, list[ModVersion]] = {}
    for version in versions:
        versions_by_mod_id.setdefault(version.mod_id, []).append(version)

    resolved: dict[str, ModVersion] = {}
    for selected_mod in config.selected_mods:
        matched = _match_selected_mod(selected_mod=selected_mod, version_map=version_map, versions_by_mod_id=versions_by_mod_id)
        if matched is not None:
            resolved[selected_mod.mod_id] = matched
    return resolved


def has_error_issues(report: CompatibilityReport) -> bool:
    return any(issue.severity == IssueSeverity.ERROR.value for issue in report.issues)


def error_issue_count(report: CompatibilityReport) -> int:
    return sum(issue.severity == IssueSeverity.ERROR.value for issue in report.issues)


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
