"""Seeded dependency-dense case generation and inverse-valid injections."""

from __future__ import annotations

from collections import defaultdict
import random

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modpack_solver.final_dataset.repair_trace import replay_repair_plan
from modpack_solver.final_dataset.topology import DependencyTopology, build_required_topology
from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.models import (
    Dependency,
    DependencyType,
    MetadataSource,
    ModProject,
    ModVersion,
    ModpackConfig,
    RepairAction,
    RepairActionType,
    SelectedMod,
    SyntheticCase,
)
from modpack_solver.solver.checker import IssueSeverity, check_graph
from modpack_solver.solver.costs import RepairWeights, action_cost


class StressCaseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    selected_mod_count: int = Field(ge=1)
    topology: DependencyTopology
    target_required_edge_count: int = Field(ge=0)
    target_maximum_depth: int = Field(ge=0)
    target_branching_factor: int = Field(ge=1)
    candidate_versions_per_choice_mod: int = Field(ge=1)
    choice_mod_fraction: float = Field(ge=0.0, le=1.0)
    optional_edge_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    conflict_edge_count: int = Field(default=0, ge=0)
    embedded_edge_count: int = Field(default=0, ge=0)
    seed: int

    @model_validator(mode="after")
    def validate_targets(self) -> "StressCaseConfig":
        if not self.case_id.strip():
            raise ValueError("case_id cannot be empty.")
        if self.target_maximum_depth >= self.selected_mod_count:
            raise ValueError("target_maximum_depth must be lower than selected_mod_count.")
        return self


class GeneratedStressVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: SyntheticCase
    known_valid_repair: list[RepairAction]
    changed_mod_ids: list[str] = Field(default_factory=list)
    description: str


def build_valid_stress_case(config: StressCaseConfig) -> SyntheticCase:
    """Build a checker-valid case with the requested deterministic topology."""

    prefix = config.case_id
    projects = [
        ModProject(
            mod_id=f"{prefix}-mod-{index:03d}",
            name=f"{prefix.replace('-', ' ').title()} Mod {index:03d}",
            slug=f"{prefix}-mod-{index:03d}",
            source=MetadataSource.SYNTHETIC,
        )
        for index in range(config.selected_mod_count)
    ]
    base_versions = [
        ModVersion(
            version_id=f"{project.mod_id}-v1",
            mod_id=project.mod_id,
            version_number="1.0.0",
            game_versions=["1.20.1"],
            loaders=["fabric"],
        )
        for project in projects
    ]
    selected = [
        SelectedMod(
            mod_id=version.mod_id,
            version_id=version.version_id,
            version_number=version.version_number,
        )
        for version in base_versions
    ]

    required_edges = build_required_topology(
        node_count=config.selected_mod_count,
        topology=config.topology,
        target_edge_count=config.target_required_edge_count,
        target_depth=config.target_maximum_depth,
        branching_factor=config.target_branching_factor,
        seed=config.seed,
    )
    dependencies_by_source: dict[int, list[Dependency]] = defaultdict(list)
    occupied = set(required_edges)
    for source, target in sorted(required_edges):
        dependencies_by_source[source].append(
            Dependency(
                target_mod_id=projects[target].mod_id,
                target_version_id=base_versions[target].version_id,
                dependency_type=DependencyType.REQUIRED,
                source=MetadataSource.SYNTHETIC,
            )
        )

    rng = random.Random(config.seed + 101)
    possible_pairs = [
        (source, target)
        for source in range(config.selected_mod_count)
        for target in range(config.selected_mod_count)
        if source != target and (source, target) not in occupied
    ]
    rng.shuffle(possible_pairs)
    optional_count = round(len(required_edges) * config.optional_edge_fraction)
    for source, target in _take_pairs(possible_pairs, occupied, optional_count):
        dependencies_by_source[source].append(
            Dependency(
                target_mod_id=projects[target].mod_id,
                dependency_type=DependencyType.OPTIONAL,
                source=MetadataSource.SYNTHETIC,
            )
        )

    for index in range(config.conflict_edge_count):
        source = index % config.selected_mod_count
        target_project = ModProject(
            mod_id=f"{prefix}-unselected-conflict-{index:03d}",
            name=f"Unselected Conflict Target {index:03d}",
            source=MetadataSource.SYNTHETIC,
        )
        target_version = ModVersion(
            version_id=f"{target_project.mod_id}-v1",
            mod_id=target_project.mod_id,
            version_number="1.0.0",
            game_versions=["1.20.1"],
            loaders=["fabric"],
        )
        projects.append(target_project)
        base_versions.append(target_version)
        dependencies_by_source[source].append(
            Dependency(
                target_mod_id=target_project.mod_id,
                dependency_type=DependencyType.INCOMPATIBLE,
                source=MetadataSource.SYNTHETIC,
            )
        )

    for source, target in _take_pairs(
        possible_pairs,
        occupied,
        config.embedded_edge_count,
    ):
        dependencies_by_source[source].append(
            Dependency(
                target_mod_id=projects[target].mod_id,
                dependency_type=DependencyType.EMBEDDED,
                source=MetadataSource.SYNTHETIC,
            )
        )

    for index in range(config.selected_mod_count):
        base_versions[index].dependencies = dependencies_by_source[index]

    versions = list(base_versions)
    choice_count = round(config.selected_mod_count * config.choice_mod_fraction)
    choice_indices = sorted(
        random.Random(config.seed + 303).sample(
            range(config.selected_mod_count),
            min(choice_count, config.selected_mod_count),
        )
    )
    for index in choice_indices:
        selected_version = base_versions[index]
        for alternative_index in range(2, config.candidate_versions_per_choice_mod + 1):
            dependencies = [
                dependency.model_copy(deep=True)
                for dependency in selected_version.dependencies
            ]
            if (
                alternative_index == config.candidate_versions_per_choice_mod
                and config.candidate_versions_per_choice_mod >= 3
                and config.selected_mod_count > 1
            ):
                conflict_target = projects[(index + 1) % config.selected_mod_count].mod_id
                dependencies.append(
                    Dependency(
                        target_mod_id=conflict_target,
                        dependency_type=DependencyType.INCOMPATIBLE,
                        source=MetadataSource.SYNTHETIC,
                    )
                )
            versions.append(
                ModVersion(
                    version_id=f"{selected_version.mod_id}-v{alternative_index}",
                    mod_id=selected_version.mod_id,
                    version_number=f"{alternative_index}.0.0",
                    game_versions=["1.20.1"],
                    loaders=["fabric"],
                    dependencies=dependencies,
                )
            )

    case = SyntheticCase(
        config=ModpackConfig(
            minecraft_version="1.20.1",
            loader="fabric",
            selected_mods=selected,
        ),
        projects=projects,
        versions=versions,
    )
    report = check_graph(build_graph_from_synthetic_case(case))
    if any(issue.severity == IssueSeverity.ERROR.value for issue in report.issues):
        raise ValueError(
            f"Generated stress control '{config.case_id}' is not compatible: {report.summary}"
        )
    return case


def inject_missing_required_selection(case: SyntheticCase) -> GeneratedStressVariant:
    """Remove a selected required target and retain its metadata for inverse repair."""

    modified = case.model_copy(deep=True)
    selected_ids = {selected.mod_id for selected in modified.config.selected_mods}
    inbound: dict[str, int] = defaultdict(int)
    for version in _selected_versions(modified):
        for dependency in version.dependencies:
            if (
                dependency.dependency_type == DependencyType.REQUIRED
                and dependency.target_mod_id in selected_ids
            ):
                inbound[dependency.target_mod_id] += 1
    if not inbound:
        raise ValueError("Stress control has no selected required target to remove.")
    target_mod_id = sorted(inbound, key=lambda item: (-inbound[item], item))[0]
    target_version = next(
        version
        for version in modified.versions
        if version.mod_id == target_mod_id and version.version_id.endswith("-v1")
    )
    modified.config.selected_mods = [
        selected
        for selected in modified.config.selected_mods
        if selected.mod_id != target_mod_id
    ]
    action = _priced_action(
        RepairActionType.ADD_DEPENDENCY,
        target_mod_id,
        target_version,
    )
    variant = GeneratedStressVariant(
        case=modified,
        known_valid_repair=[action],
        changed_mod_ids=[target_mod_id],
        description=(
            f"Removed selected required dependency '{target_mod_id}'; the inverse add "
            "is a known valid repair."
        ),
    )
    if not replay_repair_plan(variant.case, variant.known_valid_repair).final_compatible:
        raise ValueError("Inverse missing-dependency repair did not restore compatibility.")
    return variant


def inject_selected_version_mismatch(case: SyntheticCase) -> GeneratedStressVariant:
    """Select a deliberately incompatible version with a known inverse upgrade."""

    modified = case.model_copy(deep=True)
    selected_version = _selected_versions(modified)[0]
    bad_version = selected_version.model_copy(
        update={
            "version_id": f"{selected_version.mod_id}-v0-incompatible",
            "version_number": "0.1.0",
            "game_versions": ["1.19.4"],
        },
        deep=True,
    )
    modified.versions.append(bad_version)
    for index, selected in enumerate(modified.config.selected_mods):
        if selected.mod_id == selected_version.mod_id:
            modified.config.selected_mods[index] = SelectedMod(
                mod_id=bad_version.mod_id,
                version_id=bad_version.version_id,
                version_number=bad_version.version_number,
            )
            break
    action = _priced_action(
        RepairActionType.UPGRADE_MOD,
        selected_version.mod_id,
        selected_version,
    )
    variant = GeneratedStressVariant(
        case=modified,
        known_valid_repair=[action],
        changed_mod_ids=[selected_version.mod_id],
        description=(
            f"Selected an incompatible Minecraft version for '{selected_version.mod_id}'; "
            "restoring the original version is a known valid repair."
        ),
    )
    if not replay_repair_plan(variant.case, variant.known_valid_repair).final_compatible:
        raise ValueError("Inverse version repair did not restore compatibility.")
    return variant


def _selected_versions(case: SyntheticCase) -> list[ModVersion]:
    version_map = {version.version_id: version for version in case.versions}
    return [
        version_map[selected.version_id]
        for selected in case.config.selected_mods
        if selected.version_id in version_map
    ]


def _take_pairs(
    pairs: list[tuple[int, int]],
    occupied: set[tuple[int, int]],
    count: int,
) -> list[tuple[int, int]]:
    if count <= 0:
        return []
    chosen = []
    for pair in pairs:
        if pair in occupied:
            continue
        occupied.add(pair)
        chosen.append(pair)
        if len(chosen) >= count:
            break
    return chosen


def _priced_action(
    action_type: RepairActionType,
    target_mod_id: str,
    version: ModVersion,
) -> RepairAction:
    action = RepairAction(
        action_type=action_type,
        target_mod_id=target_mod_id,
        target_version_id=version.version_id,
        target_version_number=version.version_number,
        reason="Inverse of the deterministic injected change.",
    )
    action.cost = action_cost(action, RepairWeights())
    return action
