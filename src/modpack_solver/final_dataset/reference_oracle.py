"""Independent bounded enumeration oracle for small controlled cases.

The oracle deliberately does not reuse the weighted search frontier, candidate
ordering, or solution-priority functions. It enumerates complete selections and
uses only the shared compatibility checker to decide whether each is valid.
"""

from __future__ import annotations

from collections import Counter
from itertools import product
from math import prod

from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.models import (
    DependencyType,
    ModVersion,
    ModpackConfig,
    RepairAction,
    RepairActionType,
    SelectedMod,
    SyntheticCase,
)
from modpack_solver.solver.checker import IssueSeverity
from modpack_solver.solver.common import evaluate_config
from modpack_solver.solver.costs import RepairWeights, action_cost
from modpack_solver.versioning import VersionDirection, compare_versions


class ReferenceOracleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid_configurations_found: int = Field(ge=0)
    minimum_default_cost: int | None = Field(default=None, ge=0)
    minimum_preservation_cost: int | None = Field(default=None, ge=0)
    minimum_action_count: int | None = Field(default=None, ge=0)
    best_default_actions: list[RepairAction] = Field(default_factory=list)
    best_preservation_actions: list[RepairAction] = Field(default_factory=list)
    exhaustive: bool
    configurations_checked: int = Field(ge=0)


def enumerate_reference_repairs(
    case: SyntheticCase,
    *,
    max_configurations: int = 100_000,
) -> ReferenceOracleResult:
    """Enumerate bounded project/version presence choices for a small case."""

    if max_configurations < 1:
        raise ValueError("max_configurations must be at least 1.")

    versions_by_mod: dict[str, list[ModVersion]] = {}
    for version in sorted(case.versions, key=lambda item: (item.mod_id, item.version_id)):
        versions_by_mod.setdefault(version.mod_id, []).append(version)

    original_mod_ids = {selected.mod_id for selected in case.config.selected_mods}
    removable_mod_ids = {
        mod_id
        for version in case.versions
        for dependency in version.dependencies
        if dependency.dependency_type == DependencyType.INCOMPATIBLE
        for mod_id in (version.mod_id, dependency.target_mod_id)
    }
    required_mod_ids = {
        dependency.target_mod_id
        for version in case.versions
        for dependency in version.dependencies
        if dependency.dependency_type == DependencyType.REQUIRED
        and dependency.target_mod_id in versions_by_mod
    }
    decision_mod_ids = sorted(original_mod_ids | required_mod_ids)
    choices: list[list[ModVersion | None]] = []
    for mod_id in decision_mod_ids:
        available = list(versions_by_mod.get(mod_id, []))
        if mod_id not in original_mod_ids or mod_id in removable_mod_ids:
            choices.append([None, *available])
        else:
            choices.append(available)

    total_combinations = prod(len(options) for options in choices)
    exhaustive = total_combinations <= max_configurations
    default_weights = RepairWeights()
    preservation_weights = RepairWeights(
        add_required_dependency=1,
        upgrade_dependency=2,
        downgrade_dependency=3,
        upgrade_selected_mod=5,
        downgrade_selected_mod=6,
        remove_selected_mod=20,
        change_minecraft_version=20,
        change_loader=25,
    )

    valid_count = 0
    checked = 0
    best_default: tuple[tuple, list[RepairAction]] | None = None
    best_preservation: tuple[tuple, list[RepairAction]] | None = None
    minimum_action_count: int | None = None

    for selection in product(*choices):
        if checked >= max_configurations:
            exhaustive = False
            break
        checked += 1
        selected_versions = [version for version in selection if version is not None]
        config = ModpackConfig(
            minecraft_version=case.config.minecraft_version,
            loader=case.config.loader,
            selected_mods=[
                SelectedMod(
                    mod_id=version.mod_id,
                    version_id=version.version_id,
                    version_number=version.version_number,
                )
                for version in selected_versions
            ],
        )
        report = evaluate_config(config, case.projects, case.versions)
        if any(issue.severity == IssueSeverity.ERROR.value for issue in report.issues):
            continue

        actions = _actions_from_configuration(case, selected_versions, default_weights)
        if actions is None:
            continue
        valid_count += 1
        minimum_action_count = (
            len(actions)
            if minimum_action_count is None
            else min(minimum_action_count, len(actions))
        )

        default_actions = _reprice(actions, default_weights)
        default_rank = _plan_rank(default_actions, config)
        if best_default is None or default_rank < best_default[0]:
            best_default = (default_rank, default_actions)

        preservation_actions = _reprice(actions, preservation_weights)
        preservation_rank = _plan_rank(preservation_actions, config)
        if best_preservation is None or preservation_rank < best_preservation[0]:
            best_preservation = (preservation_rank, preservation_actions)

    return ReferenceOracleResult(
        valid_configurations_found=valid_count,
        minimum_default_cost=best_default[0][0] if best_default else None,
        minimum_preservation_cost=best_preservation[0][0] if best_preservation else None,
        minimum_action_count=minimum_action_count,
        best_default_actions=best_default[1] if best_default else [],
        best_preservation_actions=best_preservation[1] if best_preservation else [],
        exhaustive=exhaustive,
        configurations_checked=checked,
    )


def _actions_from_configuration(
    case: SyntheticCase,
    selected_versions: list[ModVersion],
    weights: RepairWeights,
) -> list[RepairAction] | None:
    original_by_mod: dict[str, list[SelectedMod]] = {}
    for selected in case.config.selected_mods:
        original_by_mod.setdefault(selected.mod_id, []).append(selected)
    candidate_by_mod = {version.mod_id: version for version in selected_versions}
    actions: list[RepairAction] = []

    for mod_id in sorted(set(original_by_mod) | set(candidate_by_mod)):
        originals = original_by_mod.get(mod_id, [])
        candidate = candidate_by_mod.get(mod_id)
        if candidate is None:
            if originals:
                actions.append(_action(RepairActionType.REMOVE_MOD, mod_id, weights))
            continue
        if not originals:
            actions.append(
                _action(
                    RepairActionType.ADD_DEPENDENCY,
                    mod_id,
                    weights,
                    candidate,
                )
            )
            continue
        if len(originals) > 1:
            actions.append(_action(RepairActionType.REMOVE_MOD, mod_id, weights))

        original_version = _resolve_original_version(originals, case.versions)
        if original_version is None or original_version.version_id == candidate.version_id:
            continue
        direction = compare_versions(original_version.version_number, candidate.version_number)
        if direction == VersionDirection.UPGRADE:
            action_type = RepairActionType.UPGRADE_MOD
        elif direction == VersionDirection.DOWNGRADE:
            action_type = RepairActionType.DOWNGRADE_MOD
        else:
            return None
        actions.append(_action(action_type, mod_id, weights, candidate))
    return sorted(
        actions,
        key=lambda action: (
            action.action_type.value,
            action.target_mod_id,
            action.target_version_id or "",
        ),
    )


def _resolve_original_version(
    selections: list[SelectedMod],
    versions: list[ModVersion],
) -> ModVersion | None:
    version_map = {version.version_id: version for version in versions}
    for selected in sorted(
        selections,
        key=lambda item: (item.version_id or "", item.version_number or ""),
    ):
        if selected.version_id and selected.version_id in version_map:
            return version_map[selected.version_id]
        if selected.version_number:
            match = next(
                (
                    version
                    for version in versions
                    if version.mod_id == selected.mod_id
                    and version.version_number == selected.version_number
                ),
                None,
            )
            if match:
                return match
    return None


def _action(
    action_type: RepairActionType,
    mod_id: str,
    weights: RepairWeights,
    version: ModVersion | None = None,
) -> RepairAction:
    action = RepairAction(
        action_type=action_type,
        target_mod_id=mod_id,
        target_version_id=version.version_id if version else None,
        target_version_number=version.version_number if version else None,
        reason="Independent exhaustive reference configuration.",
    )
    action.cost = action_cost(action, weights)
    return action


def _reprice(actions: list[RepairAction], weights: RepairWeights) -> list[RepairAction]:
    return [
        action.model_copy(update={"cost": action_cost(action, weights)}, deep=True)
        for action in actions
    ]


def _plan_rank(actions: list[RepairAction], config: ModpackConfig) -> tuple:
    removed = Counter(action.action_type == RepairActionType.REMOVE_MOD for action in actions)[True]
    return (
        sum(action.cost for action in actions),
        removed,
        len(actions),
        tuple(
            (action.action_type.value, action.target_mod_id, action.target_version_id or "")
            for action in actions
        ),
        tuple(
            sorted(
                (selected.mod_id, selected.version_id or "")
                for selected in config.selected_mods
            )
        ),
    )
