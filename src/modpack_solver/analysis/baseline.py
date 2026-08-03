"""Deterministic execution of simple baseline repair suggestions."""

from __future__ import annotations

from collections.abc import Sequence

from modpack_solver.analysis.models import BaselineExecutionResult
from modpack_solver.models import ModpackConfig, RepairAction, RepairActionType, SyntheticCase
from modpack_solver.solver import evaluate_config
from modpack_solver.solver.common import compatible_versions_for_mod, resolve_selected_versions
from modpack_solver.solver.search import apply_repair_action
from modpack_solver.solver.state import (
    SolverState,
    count_original_mods_preserved,
    count_removed_original_mods,
    count_version_changes,
)
from modpack_solver.versioning import VersionDirection, compare_versions


def baseline_suggestions_for_case(case: SyntheticCase) -> list[RepairAction]:
    """Return existing baseline suggestions for a case without adding search behavior."""

    report = evaluate_config(case.config, case.projects, case.versions)
    return [action.model_copy(deep=True) for action in report.repair_actions]


def apply_baseline_suggestions(
    case: SyntheticCase,
    suggestions: Sequence[RepairAction],
) -> BaselineExecutionResult:
    """Apply baseline suggestions once, in order, without backtracking."""

    state = SolverState(config=case.config.model_copy(deep=True))
    executable_actions: list[RepairAction] = []
    unexecutable_suggestions: list[RepairAction] = []

    for suggestion in suggestions:
        concrete = _concretize_suggestion(case, state.config, suggestion)
        if concrete is None:
            unexecutable_suggestions.append(suggestion.model_copy(deep=True))
            continue

        next_state = apply_repair_action(state=state, action=concrete, versions=case.versions)
        if next_state is None:
            unexecutable_suggestions.append(suggestion.model_copy(deep=True))
            continue

        state = next_state
        executable_actions.append(concrete)

    final_report = evaluate_config(state.config, case.projects, case.versions)
    final_compatible = not any(issue.severity == "error" for issue in final_report.issues)
    return BaselineExecutionResult(
        suggestions=[suggestion.model_copy(deep=True) for suggestion in suggestions],
        executable_actions=executable_actions,
        unexecutable_suggestions=unexecutable_suggestions,
        repaired_config=state.config.model_copy(deep=True),
        final_report=final_report,
        final_compatible=final_compatible,
        original_mods_preserved=count_original_mods_preserved(case.config, state.config),
        removed_mod_count=count_removed_original_mods(case.config, state.config),
        version_change_count=count_version_changes(case.config, state.config),
    )


def _concretize_suggestion(
    case: SyntheticCase,
    config: ModpackConfig,
    suggestion: RepairAction,
) -> RepairAction | None:
    if suggestion.action_type == RepairActionType.ADD_DEPENDENCY:
        if _is_selected(config, suggestion.target_mod_id):
            return None
        candidates = compatible_versions_for_mod(suggestion.target_mod_id, config, case.versions)
        if not candidates:
            return None
        candidate = candidates[0]
        return suggestion.model_copy(
            update={
                "target_version_id": candidate.version_id,
                "target_version_number": candidate.version_number,
            },
            deep=True,
        )

    if suggestion.action_type == RepairActionType.REMOVE_MOD:
        if not _is_selected(config, suggestion.target_mod_id):
            return None
        return suggestion.model_copy(deep=True)

    if suggestion.action_type in {
        RepairActionType.UPGRADE_DEPENDENCY,
        RepairActionType.DOWNGRADE_DEPENDENCY,
        RepairActionType.UPGRADE_MOD,
        RepairActionType.DOWNGRADE_MOD,
    }:
        selected_versions = resolve_selected_versions(config, case.versions)
        current = selected_versions.get(suggestion.target_mod_id)
        if current is None:
            return None
        for candidate in compatible_versions_for_mod(suggestion.target_mod_id, config, case.versions):
            if candidate.version_id == current.version_id:
                continue
            direction = compare_versions(current.version_number, candidate.version_number)
            if direction == VersionDirection.UNKNOWN or direction == VersionDirection.SAME:
                continue
            action_type = (
                RepairActionType.DOWNGRADE_MOD
                if direction == VersionDirection.DOWNGRADE
                else RepairActionType.UPGRADE_MOD
            )
            return suggestion.model_copy(
                update={
                    "action_type": action_type,
                    "target_version_id": candidate.version_id,
                    "target_version_number": candidate.version_number,
                },
                deep=True,
            )
        return None

    return None


def _is_selected(config: ModpackConfig, mod_id: str) -> bool:
    return any(selected.mod_id == mod_id for selected in config.selected_mods)
