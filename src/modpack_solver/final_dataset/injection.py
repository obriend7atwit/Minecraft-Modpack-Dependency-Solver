"""Deterministic, non-mutating error injection for compatibility cases."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.models import (
    DependencyType,
    IssueType,
    SelectedMod,
    SyntheticCase,
)
from modpack_solver.models import RepairActionType
from modpack_solver.solver import SolverStatus
from modpack_solver.solver.checker import check_graph
from modpack_solver.final_dataset.models import InjectedCaseResult, ModificationType


def inject_remove_required_dependency(
    case: SyntheticCase,
    *,
    target_mod_id: str | None = None,
) -> InjectedCaseResult:
    modified = case.model_copy(deep=True)
    required_targets = _selected_required_targets(modified)
    target = _choose_target(required_targets, target_mod_id, "selected required dependency")
    before = len(modified.config.selected_mods)
    modified.config.selected_mods = [
        selected for selected in modified.config.selected_mods if selected.mod_id != target
    ]
    if len(modified.config.selected_mods) == before:
        raise ValueError(f"Required dependency '{target}' is not selected and cannot be removed.")
    return _build_result(
        modified,
        ModificationType.REMOVE_REQUIRED_DEPENDENCY,
        f"Removed required dependency '{target}' from the selected mod list.",
        changed_mod_ids=[target],
    )


def inject_minecraft_version_mismatch(
    case: SyntheticCase,
    *,
    new_minecraft_version: str,
) -> InjectedCaseResult:
    value = new_minecraft_version.strip()
    if not value or value == case.config.minecraft_version:
        raise ValueError("new_minecraft_version must be nonempty and different from the original.")
    modified = case.model_copy(deep=True)
    original = modified.config.minecraft_version
    modified.config.minecraft_version = value
    return _build_result(
        modified,
        ModificationType.CHANGE_MINECRAFT_VERSION,
        f"Changed Minecraft version from '{original}' to '{value}'.",
        changed_mod_ids=sorted({selected.mod_id for selected in modified.config.selected_mods}),
    )


def inject_loader_mismatch(
    case: SyntheticCase,
    *,
    new_loader: str,
) -> InjectedCaseResult:
    value = new_loader.strip().lower()
    if not value or value == case.config.loader.lower():
        raise ValueError("new_loader must be nonempty and different from the original loader.")
    modified = case.model_copy(deep=True)
    original = modified.config.loader
    modified.config.loader = value
    return _build_result(
        modified,
        ModificationType.CHANGE_LOADER,
        f"Changed loader from '{original}' to '{value}'.",
        changed_mod_ids=sorted({selected.mod_id for selected in modified.config.selected_mods}),
    )


def inject_incompatible_version(
    case: SyntheticCase,
    *,
    target_mod_id: str | None = None,
) -> InjectedCaseResult:
    modified = case.model_copy(deep=True)
    selected_ids = [selected.mod_id for selected in modified.config.selected_mods]
    candidates = []
    for mod_id in sorted(set(selected_ids)):
        if target_mod_id and mod_id != target_mod_id:
            continue
        for version in sorted(modified.versions, key=lambda item: item.version_id):
            if version.mod_id != mod_id:
                continue
            if (
                modified.config.minecraft_version not in version.game_versions
                or modified.config.loader not in version.loaders
            ):
                candidates.append(version)
    if not candidates:
        target_text = f" for '{target_mod_id}'" if target_mod_id else ""
        raise ValueError(f"No incompatible alternative version is available{target_text}.")
    replacement = candidates[0]
    for index, selected in enumerate(modified.config.selected_mods):
        if selected.mod_id == replacement.mod_id:
            modified.config.selected_mods[index] = SelectedMod(
                mod_id=replacement.mod_id,
                version_id=replacement.version_id,
                version_number=replacement.version_number,
            )
            break
    return _build_result(
        modified,
        ModificationType.REPLACE_WITH_INCOMPATIBLE_VERSION,
        f"Replaced '{replacement.mod_id}' with incompatible version '{replacement.version_number}'.",
        changed_mod_ids=[replacement.mod_id],
    )


def inject_add_conflicting_mod(
    case: SyntheticCase,
    *,
    target_mod_id: str | None = None,
) -> InjectedCaseResult:
    modified = case.model_copy(deep=True)
    selected_ids = {selected.mod_id for selected in modified.config.selected_mods}
    resolved = _resolved_selected_versions(modified)
    possibilities: list[tuple[str, object]] = []
    for source_id, source_version in sorted(resolved.items()):
        for dependency in source_version.dependencies:
            if dependency.dependency_type != DependencyType.INCOMPATIBLE:
                continue
            if dependency.target_mod_id in selected_ids:
                continue
            if target_mod_id and dependency.target_mod_id != target_mod_id:
                continue
            versions = [
                version
                for version in modified.versions
                if version.mod_id == dependency.target_mod_id
                and modified.config.minecraft_version in version.game_versions
                and modified.config.loader in version.loaders
            ]
            if versions:
                possibilities.append((source_id, sorted(versions, key=lambda item: item.version_id)[0]))
    if not possibilities:
        raise ValueError("No unselected conflicting mod with compatible metadata is available.")
    source_id, version = possibilities[0]
    modified.config.selected_mods.append(
        SelectedMod(
            mod_id=version.mod_id,
            version_id=version.version_id,
            version_number=version.version_number,
        )
    )
    return _build_result(
        modified,
        ModificationType.ADD_CONFLICTING_MOD,
        f"Added '{version.mod_id}', which conflicts with selected mod '{source_id}'.",
        changed_mod_ids=[source_id, version.mod_id],
    )


def inject_duplicate_mod_version(
    case: SyntheticCase,
    *,
    target_mod_id: str | None = None,
) -> InjectedCaseResult:
    modified = case.model_copy(deep=True)
    selections = sorted(
        modified.config.selected_mods,
        key=lambda selected: (selected.mod_id, selected.version_id or "", selected.version_number or ""),
    )
    if target_mod_id:
        selections = [selected for selected in selections if selected.mod_id == target_mod_id]
    if not selections:
        raise ValueError("No selected mod is available to duplicate.")
    selected = selections[0]
    alternatives = sorted(
        [version for version in modified.versions if version.mod_id == selected.mod_id and version.version_id != selected.version_id],
        key=lambda version: version.version_id,
    )
    if alternatives:
        version = alternatives[0]
        duplicate = SelectedMod(
            mod_id=version.mod_id,
            version_id=version.version_id,
            version_number=version.version_number,
        )
    else:
        duplicate = selected.model_copy(deep=True)
    modified.config.selected_mods.append(duplicate)
    return _build_result(
        modified,
        ModificationType.DUPLICATE_MOD_VERSION,
        f"Added a second selected version entry for '{selected.mod_id}'.",
        changed_mod_ids=[selected.mod_id],
    )


def inject_remove_dependency_metadata(
    case: SyntheticCase,
    *,
    target_mod_id: str | None = None,
) -> InjectedCaseResult:
    modified = case.model_copy(deep=True)
    required_targets = _all_required_targets(modified)
    target = _choose_target(required_targets, target_mod_id, "required dependency metadata")
    projects_before = len(modified.projects)
    versions_before = len(modified.versions)
    modified.projects = [project for project in modified.projects if project.mod_id != target]
    modified.versions = [version for version in modified.versions if version.mod_id != target]
    if len(modified.projects) == projects_before and len(modified.versions) == versions_before:
        raise ValueError(f"No metadata exists for required dependency '{target}'.")
    return _build_result(
        modified,
        ModificationType.REMOVE_DEPENDENCY_METADATA,
        f"Removed project and version metadata for required dependency '{target}'.",
        changed_mod_ids=[target],
    )


def inject_multi_error(
    case: SyntheticCase,
    injection_plan: Sequence[ModificationType],
) -> InjectedCaseResult:
    if len(injection_plan) < 2:
        raise ValueError("A multi-error plan must contain at least two modifications.")
    modified = case.model_copy(deep=True)
    descriptions: list[str] = []
    changed: list[str] = []
    applied: list[ModificationType] = []
    for modification in injection_plan:
        modification = ModificationType(modification)
        if modification == ModificationType.REMOVE_REQUIRED_DEPENDENCY:
            result = inject_remove_required_dependency(modified)
        elif modification == ModificationType.CHANGE_MINECRAFT_VERSION:
            result = inject_minecraft_version_mismatch(modified, new_minecraft_version="0.0-test")
        elif modification == ModificationType.CHANGE_LOADER:
            result = inject_loader_mismatch(modified, new_loader="injected-loader")
        elif modification == ModificationType.REPLACE_WITH_INCOMPATIBLE_VERSION:
            result = inject_incompatible_version(modified)
        elif modification == ModificationType.ADD_CONFLICTING_MOD:
            result = inject_add_conflicting_mod(modified)
        elif modification == ModificationType.DUPLICATE_MOD_VERSION:
            result = inject_duplicate_mod_version(modified)
        elif modification == ModificationType.REMOVE_DEPENDENCY_METADATA:
            result = inject_remove_dependency_metadata(modified)
        else:
            raise ValueError(f"Modification '{modification.value}' is not supported in a multi-error plan.")
        modified = result.modified_case
        descriptions.append(result.modification_description)
        changed.extend(result.changed_mod_ids)
        applied.append(modification)
    return _build_result(
        modified,
        ModificationType.MULTI_ERROR,
        "Applied multiple controlled changes: " + " ".join(descriptions),
        changed_mod_ids=sorted(set(changed)),
        applied_modifications=applied,
    )


def write_injection_log(result: InjectedCaseResult, path: str | Path) -> Path:
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump(mode="json", exclude={"modified_case"})
    log_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return log_path


def _build_result(
    modified_case: SyntheticCase,
    modification_type: ModificationType,
    description: str,
    *,
    changed_mod_ids: list[str],
    applied_modifications: list[ModificationType] | None = None,
) -> InjectedCaseResult:
    report = check_graph(build_graph_from_synthetic_case(modified_case))
    expected_actions, repairable = _construction_expectation(modified_case, report)
    status = SolverStatus.SOLUTION_FOUND if repairable else SolverStatus.NO_SOLUTION
    if report.status.value != "incompatible":
        status = SolverStatus.ALREADY_COMPATIBLE
    return InjectedCaseResult(
        modified_case=modified_case,
        modification_type=modification_type,
        modification_description=description,
        expected_issue_types=_stable_unique([issue.issue_type for issue in report.issues]),
        expected_action_types=expected_actions,
        expected_solver_status=status,
        expected_final_compatible=status != SolverStatus.NO_SOLUTION,
        changed_mod_ids=changed_mod_ids,
        applied_modifications=applied_modifications or [modification_type],
        notes="Expected labels were derived from the controlled injection, not solver output.",
    )


def _construction_expectation(case, report):
    actions = []
    repairable = True
    for issue in report.issues:
        if issue.severity != "error":
            continue
        if issue.issue_type == IssueType.MISSING_DEPENDENCY:
            target = issue.affected_mod_ids[-1] if issue.affected_mod_ids else ""
            if any(
                version.mod_id == target
                and case.config.minecraft_version in version.game_versions
                and case.config.loader in version.loaders
                for version in case.versions
            ):
                actions.append(RepairActionType.ADD_DEPENDENCY)
            else:
                repairable = False
        elif issue.issue_type in {
            IssueType.MINECRAFT_VERSION_MISMATCH,
            IssueType.LOADER_MISMATCH,
        }:
            target = issue.affected_mod_ids[0] if issue.affected_mod_ids else ""
            if any(
                version.mod_id == target
                and case.config.minecraft_version in version.game_versions
                and case.config.loader in version.loaders
                for version in case.versions
            ):
                actions.append(RepairActionType.UPGRADE_MOD)
            else:
                repairable = False
        elif issue.issue_type in {
            IssueType.HARD_CONFLICT,
            IssueType.DUPLICATE_MOD_VERSION,
        }:
            actions.append(RepairActionType.REMOVE_MOD)
        else:
            repairable = False
    return _stable_unique(actions), repairable


def _selected_required_targets(case: SyntheticCase) -> list[str]:
    selected = {selected.mod_id for selected in case.config.selected_mods}
    return [target for target in _all_required_targets(case) if target in selected]


def _all_required_targets(case: SyntheticCase) -> list[str]:
    resolved = _resolved_selected_versions(case)
    targets = []
    for version in resolved.values():
        targets.extend(
            dependency.target_mod_id
            for dependency in version.dependencies
            if dependency.dependency_type == DependencyType.REQUIRED
        )
    return sorted(set(targets))


def _resolved_selected_versions(case: SyntheticCase):
    version_map = {version.version_id: version for version in case.versions}
    resolved = {}
    for selected in case.config.selected_mods:
        version = version_map.get(selected.version_id) if selected.version_id else None
        if version is None and selected.version_number:
            version = next(
                (
                    item
                    for item in case.versions
                    if item.mod_id == selected.mod_id and item.version_number == selected.version_number
                ),
                None,
            )
        if version is not None:
            resolved[selected.mod_id] = version
    return resolved


def _choose_target(values: list[str], requested: str | None, label: str) -> str:
    if requested:
        if requested not in values:
            raise ValueError(f"Requested {label} '{requested}' is not available.")
        return requested
    if not values:
        raise ValueError(f"No {label} is available for injection.")
    return sorted(values)[0]


def _stable_unique(values):
    seen = set()
    ordered = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
