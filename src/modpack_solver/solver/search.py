"""Best-first weighted search over candidate repair configurations."""

from __future__ import annotations

import heapq
import itertools
import time
from typing import Sequence

from modpack_solver.models import (
    CompatibilityIssue,
    DependencyType,
    IssueType,
    ModProject,
    ModVersion,
    ModpackConfig,
    RepairAction,
    RepairActionType,
)
from modpack_solver.solver.common import (
    SearchLimits,
    SolverResult,
    SolverSolution,
    SolverStatus,
    CompatibilityReport,
    compatible_versions_for_mod,
    error_issue_count,
    evaluate_config,
    has_error_issues,
    resolve_selected_versions,
)
from modpack_solver.solver.costs import RepairWeights, action_cost
from modpack_solver.solver.state import (
    SolverState,
    add_selected_mod,
    canonical_state_key,
    count_original_mods_preserved,
    count_removed_original_mods,
    count_version_changes,
    deduplicate_selected_mod,
    remove_selected_mod,
    replace_selected_mod_version,
)
from modpack_solver.versioning import VersionDirection, compare_versions


def generate_candidate_actions(
    state: SolverState,
    report: CompatibilityReport,
    projects: Sequence[ModProject],
    versions: Sequence[ModVersion],
    weights: RepairWeights,
) -> list[RepairAction]:
    """Generate deterministic candidate repairs from the current compatibility report."""

    del projects  # Metadata already arrives through the normalized version list.

    selected_versions = resolve_selected_versions(state.config, versions)
    actions: list[RepairAction] = []

    for issue in report.issues:
        if issue.issue_type == IssueType.MISSING_DEPENDENCY:
            actions.extend(
                _generate_missing_dependency_actions(
                    state=state,
                    issue=issue,
                    selected_versions=selected_versions,
                    versions=versions,
                    weights=weights,
                )
            )
        elif issue.issue_type in {
            IssueType.MINECRAFT_VERSION_MISMATCH,
            IssueType.LOADER_MISMATCH,
        }:
            actions.extend(
                _generate_version_replacement_actions(
                    state=state,
                    mod_id=_first_mod_id(issue),
                    selected_versions=selected_versions,
                    versions=versions,
                    weights=weights,
                    reason_prefix=(
                        "Select a version that matches the configured Minecraft version and loader"
                    ),
                )
            )
        elif issue.issue_type == IssueType.HARD_CONFLICT:
            actions.extend(
                _generate_hard_conflict_actions(
                    state=state,
                    issue=issue,
                    selected_versions=selected_versions,
                    versions=versions,
                    weights=weights,
                )
            )
        elif issue.issue_type == IssueType.DUPLICATE_MOD_VERSION:
            mod_id = _first_mod_id(issue)
            if mod_id:
                actions.append(
                    _repair_action(
                        action_type=RepairActionType.REMOVE_MOD,
                        target_mod_id=mod_id,
                        weights=weights,
                        reason=f"Remove duplicate selections for '{mod_id}' while keeping one deterministic choice.",
                    )
                )

    return _deduplicate_actions(actions)


def apply_repair_action(
    state: SolverState,
    action: RepairAction,
    versions: Sequence[ModVersion],
) -> SolverState | None:
    """Apply one repair action and return a new solver state."""

    try:
        if action.action_type == RepairActionType.ADD_DEPENDENCY:
            target_version = _find_version_for_action(action, versions)
            if target_version is None:
                return None
            mod_already_selected = any(
                selected.mod_id == target_version.mod_id for selected in state.config.selected_mods
            )
            new_config = add_selected_mod(state.config, target_version)
            new_added_mod_ids = (
                state.added_mod_ids
                if mod_already_selected
                else state.added_mod_ids.union({target_version.mod_id})
            )
            new_removed_mod_ids = state.removed_mod_ids

        elif action.action_type in {
            RepairActionType.UPGRADE_DEPENDENCY,
            RepairActionType.DOWNGRADE_DEPENDENCY,
            RepairActionType.UPGRADE_MOD,
            RepairActionType.DOWNGRADE_MOD,
        }:
            target_version = _find_version_for_action(action, versions)
            if target_version is None:
                return None
            new_config = replace_selected_mod_version(state.config, action.target_mod_id, target_version)
            new_added_mod_ids = state.added_mod_ids
            new_removed_mod_ids = state.removed_mod_ids

        elif action.action_type == RepairActionType.REMOVE_MOD:
            duplicate_count = sum(
                1 for selected in state.config.selected_mods if selected.mod_id == action.target_mod_id
            )
            if duplicate_count > 1:
                new_config = deduplicate_selected_mod(state.config, action.target_mod_id)
            else:
                new_config = remove_selected_mod(state.config, action.target_mod_id)
            new_added_mod_ids = state.added_mod_ids
            new_removed_mod_ids = state.removed_mod_ids.union({action.target_mod_id})

        else:
            return None
    except ValueError:
        return None

    if canonical_state_key(new_config) == canonical_state_key(state.config):
        return None

    return SolverState(
        config=new_config,
        actions=state.actions + (action,),
        total_cost=state.total_cost + action.cost,
        added_mod_ids=new_added_mod_ids,
        removed_mod_ids=new_removed_mod_ids,
    )


def solution_priority(
    state: SolverState,
    original_config: ModpackConfig,
) -> tuple:
    """Stable priority for search frontier ordering and solution tie-breaking."""

    return (
        state.total_cost,
        -count_original_mods_preserved(original_config, state.config),
        count_removed_original_mods(original_config, state.config),
        len(state.actions),
        count_version_changes(original_config, state.config),
        canonical_state_key(state.config),
    )


def search_weighted_repairs(
    initial_config: ModpackConfig,
    projects: Sequence[ModProject],
    versions: Sequence[ModVersion],
    weights: RepairWeights,
    limits: SearchLimits,
    max_solutions: int = 1,
) -> SolverResult:
    """Run a bounded best-first search for low-cost compatible repairs."""

    if max_solutions < 1:
        raise ValueError("max_solutions must be at least 1.")

    start_time = time.monotonic()
    original_config = initial_config.model_copy(deep=True)
    initial_report = evaluate_config(original_config, projects, versions)

    if not has_error_issues(initial_report):
        runtime = time.monotonic() - start_time
        return SolverResult(
            status=SolverStatus.ALREADY_COMPATIBLE,
            original_config=original_config.model_copy(deep=True),
            repaired_config=original_config.model_copy(deep=True),
            actions=[],
            total_cost=0,
            final_report=initial_report,
            states_expanded=0,
            runtime_seconds=runtime,
            limit_reached=False,
            best_partial_config=original_config.model_copy(deep=True),
            best_partial_report=initial_report,
            solutions_found=1,
            termination_reason="Initial configuration is already compatible.",
            candidate_actions_generated=0,
            original_mods_preserved=count_original_mods_preserved(original_config, original_config),
            removed_mod_count=0,
            version_change_count=0,
        )

    initial_state = SolverState(config=original_config.model_copy(deep=True))
    initial_key = canonical_state_key(initial_state.config)
    frontier: list[tuple[tuple, int, SolverState]] = []
    counter = itertools.count()
    heapq.heappush(
        frontier,
        (solution_priority(initial_state, original_config), next(counter), initial_state),
    )

    best_cost_by_key: dict[tuple, int] = {initial_key: 0}
    report_cache: dict[tuple, CompatibilityReport] = {initial_key: initial_report}

    best_partial_state = initial_state
    best_partial_report = initial_report
    best_partial_rank = _best_partial_priority(initial_state, initial_report, original_config)

    states_expanded = 0
    candidate_actions_generated = 0
    limit_reached = False
    timed_out = False
    solutions: list[tuple[SolverState, CompatibilityReport]] = []

    while frontier:
        if time.monotonic() - start_time > limits.timeout_seconds:
            timed_out = True
            break

        if states_expanded >= limits.max_expanded_states:
            limit_reached = True
            break

        _, _, state = heapq.heappop(frontier)
        state_key = canonical_state_key(state.config)
        if state.total_cost != best_cost_by_key.get(state_key):
            continue

        report = report_cache.get(state_key)
        if report is None:
            report = evaluate_config(state.config, projects, versions)
            report_cache[state_key] = report

        states_expanded += 1

        partial_rank = _best_partial_priority(state, report, original_config)
        if partial_rank < best_partial_rank:
            best_partial_rank = partial_rank
            best_partial_state = state
            best_partial_report = report

        if not has_error_issues(report):
            solutions.append((state, report))
            if len(solutions) >= max_solutions:
                break
            continue

        if len(state.actions) >= limits.max_repair_actions:
            limit_reached = True
            continue

        actions = generate_candidate_actions(
            state=state,
            report=report,
            projects=projects,
            versions=versions,
            weights=weights,
        )
        candidate_actions_generated += len(actions)

        for action in actions:
            child_state = apply_repair_action(state=state, action=action, versions=versions)
            if child_state is None:
                continue

            child_key = canonical_state_key(child_state.config)
            best_known_cost = best_cost_by_key.get(child_key)
            if best_known_cost is not None and child_state.total_cost >= best_known_cost:
                continue

            best_cost_by_key[child_key] = child_state.total_cost
            heapq.heappush(
                frontier,
                (solution_priority(child_state, original_config), next(counter), child_state),
            )

    runtime = time.monotonic() - start_time

    if solutions:
        primary_state, primary_report = solutions[0]
        alternative_solutions = [
            SolverSolution(
                repaired_config=state.config.model_copy(deep=True),
                actions=list(state.actions),
                total_cost=state.total_cost,
                final_report=report,
            )
            for state, report in solutions[1:]
        ]
        termination_reason = "A valid weighted repair plan was found."
        if timed_out:
            termination_reason = "A valid repair was found before the search timed out."
        elif limit_reached and len(solutions) < max_solutions:
            termination_reason = "A valid repair was found before the search hit its configured limit."

        return SolverResult(
            status=SolverStatus.SOLUTION_FOUND,
            original_config=original_config.model_copy(deep=True),
            repaired_config=primary_state.config.model_copy(deep=True),
            actions=list(primary_state.actions),
            total_cost=primary_state.total_cost,
            final_report=primary_report,
            states_expanded=states_expanded,
            runtime_seconds=runtime,
            limit_reached=limit_reached,
            best_partial_config=best_partial_state.config.model_copy(deep=True),
            best_partial_report=best_partial_report,
            alternative_solutions=alternative_solutions,
            solutions_found=len(solutions),
            termination_reason=termination_reason,
            candidate_actions_generated=candidate_actions_generated,
            original_mods_preserved=count_original_mods_preserved(original_config, primary_state.config),
            removed_mod_count=count_removed_original_mods(original_config, primary_state.config),
            version_change_count=count_version_changes(original_config, primary_state.config),
        )

    status = SolverStatus.NO_SOLUTION
    termination_reason = "Search exhausted all reachable repair states without finding a valid configuration."
    if timed_out:
        status = SolverStatus.TIMEOUT
        termination_reason = "Search timed out before a valid repair was found."
    elif limit_reached:
        status = SolverStatus.LIMIT_REACHED
        termination_reason = "Search limit reached before a valid repair was found."

    return SolverResult(
        status=status,
        original_config=original_config.model_copy(deep=True),
        repaired_config=None,
        actions=[],
        total_cost=None,
        final_report=None,
        states_expanded=states_expanded,
        runtime_seconds=runtime,
        limit_reached=limit_reached,
        best_partial_config=best_partial_state.config.model_copy(deep=True),
        best_partial_report=best_partial_report,
        alternative_solutions=[],
        solutions_found=0,
        termination_reason=termination_reason,
        candidate_actions_generated=candidate_actions_generated,
        original_mods_preserved=count_original_mods_preserved(original_config, best_partial_state.config),
        removed_mod_count=count_removed_original_mods(original_config, best_partial_state.config),
        version_change_count=count_version_changes(original_config, best_partial_state.config),
    )


def _generate_missing_dependency_actions(
    state: SolverState,
    issue: CompatibilityIssue,
    selected_versions: dict[str, ModVersion],
    versions: Sequence[ModVersion],
    weights: RepairWeights,
) -> list[RepairAction]:
    source_mod_id = issue.affected_mod_ids[0] if issue.affected_mod_ids else None
    target_mod_id = issue.affected_mod_ids[1] if len(issue.affected_mod_ids) > 1 else None
    if not source_mod_id or not target_mod_id:
        return []

    source_version = selected_versions.get(source_mod_id)
    compatible_candidates = compatible_versions_for_mod(target_mod_id, state.config, versions)
    if not compatible_candidates:
        return []

    preferred_version_id: str | None = None
    if source_version is not None:
        for dependency in source_version.dependencies:
            if dependency.dependency_type != DependencyType.REQUIRED:
                continue
            if dependency.target_mod_id == target_mod_id:
                preferred_version_id = dependency.target_version_id
                break

    ordered_candidates = _preferred_first_candidates(compatible_candidates, preferred_version_id)
    selected_target_version = selected_versions.get(target_mod_id)
    actions: list[RepairAction] = []

    if selected_target_version is not None:
        for candidate in ordered_candidates:
            if candidate.version_id == selected_target_version.version_id:
                continue
            action = _build_version_change_action(
                state=state,
                mod_id=target_mod_id,
                current_version=selected_target_version,
                candidate_version=candidate,
                weights=weights,
                reason=(
                    f"Select '{candidate.version_number}' for '{target_mod_id}' so "
                    f"'{source_mod_id}' has its required dependency available."
                ),
            )
            if action is not None:
                actions.append(action)
        return actions

    for candidate in ordered_candidates:
        actions.append(
            _repair_action(
                action_type=RepairActionType.ADD_DEPENDENCY,
                target_mod_id=target_mod_id,
                target_version_id=candidate.version_id,
                target_version_number=candidate.version_number,
                weights=weights,
                reason=(
                    f"Add required dependency '{target_mod_id}' using compatible version "
                    f"'{candidate.version_number}' for '{source_mod_id}'."
                ),
            )
        )
    return actions


def _generate_version_replacement_actions(
    state: SolverState,
    mod_id: str | None,
    selected_versions: dict[str, ModVersion],
    versions: Sequence[ModVersion],
    weights: RepairWeights,
    reason_prefix: str,
) -> list[RepairAction]:
    if mod_id is None:
        return []

    current_version = selected_versions.get(mod_id)
    if current_version is None:
        return []

    actions: list[RepairAction] = []
    for candidate in compatible_versions_for_mod(mod_id, state.config, versions):
        if candidate.version_id == current_version.version_id:
            continue
        action = _build_version_change_action(
            state=state,
            mod_id=mod_id,
            current_version=current_version,
            candidate_version=candidate,
            weights=weights,
            reason=(
                f"{reason_prefix}: replace '{current_version.version_number}' with "
                f"'{candidate.version_number}' for '{mod_id}'."
            ),
        )
        if action is not None:
            actions.append(action)
    return actions


def _generate_hard_conflict_actions(
    state: SolverState,
    issue: CompatibilityIssue,
    selected_versions: dict[str, ModVersion],
    versions: Sequence[ModVersion],
    weights: RepairWeights,
) -> list[RepairAction]:
    mod_ids = [mod_id for mod_id in issue.affected_mod_ids[:2] if mod_id]
    if len(mod_ids) < 2:
        return []

    mod_a, mod_b = mod_ids
    actions: list[RepairAction] = []

    for mod_id, other_mod_id in [(mod_a, mod_b), (mod_b, mod_a)]:
        if any(selected.mod_id == mod_id for selected in state.config.selected_mods):
            actions.append(
                _repair_action(
                    action_type=RepairActionType.REMOVE_MOD,
                    target_mod_id=mod_id,
                    weights=weights,
                    reason=f"Remove '{mod_id}' to resolve its conflict with '{other_mod_id}'.",
                )
            )

        current_version = selected_versions.get(mod_id)
        if current_version is None:
            continue

        for candidate in compatible_versions_for_mod(mod_id, state.config, versions):
            if candidate.version_id == current_version.version_id:
                continue
            action = _build_version_change_action(
                state=state,
                mod_id=mod_id,
                current_version=current_version,
                candidate_version=candidate,
                weights=weights,
                reason=(
                    f"Change '{mod_id}' from '{current_version.version_number}' to "
                    f"'{candidate.version_number}' to try resolving its conflict with '{other_mod_id}'."
                ),
            )
            if action is not None:
                actions.append(action)

    return actions


def _build_version_change_action(
    state: SolverState,
    mod_id: str,
    current_version: ModVersion,
    candidate_version: ModVersion,
    weights: RepairWeights,
    reason: str,
) -> RepairAction | None:
    direction = compare_versions(current_version.version_number, candidate_version.version_number)
    is_dependency = mod_id in state.added_mod_ids

    if direction == VersionDirection.SAME:
        return None
    if direction == VersionDirection.UNKNOWN:
        return None

    if direction == VersionDirection.UPGRADE:
        action_type = (
            RepairActionType.UPGRADE_DEPENDENCY
            if is_dependency
            else RepairActionType.UPGRADE_MOD
        )
    else:
        action_type = (
            RepairActionType.DOWNGRADE_DEPENDENCY
            if is_dependency
            else RepairActionType.DOWNGRADE_MOD
        )

    return _repair_action(
        action_type=action_type,
        target_mod_id=mod_id,
        target_version_id=candidate_version.version_id,
        target_version_number=candidate_version.version_number,
        weights=weights,
        reason=reason,
    )


def _repair_action(
    *,
    action_type: RepairActionType,
    target_mod_id: str,
    weights: RepairWeights,
    target_version_id: str | None = None,
    target_version_number: str | None = None,
    reason: str | None = None,
) -> RepairAction:
    action = RepairAction(
        action_type=action_type,
        target_mod_id=target_mod_id,
        target_version_id=target_version_id,
        target_version_number=target_version_number,
        reason=reason,
    )
    action.cost = action_cost(action, weights)
    return action


def _deduplicate_actions(actions: Sequence[RepairAction]) -> list[RepairAction]:
    deduped: dict[tuple[str, str, str, str, str], RepairAction] = {}
    for action in actions:
        key = (
            action.action_type.value,
            action.target_mod_id,
            action.target_version_id or "",
            action.target_version_number or "",
            action.reason or "",
        )
        current = deduped.get(key)
        if current is None or action.cost < current.cost:
            deduped[key] = action
    return sorted(
        deduped.values(),
        key=lambda action: (
            action.cost,
            action.action_type.value,
            action.target_mod_id,
            action.target_version_number or "",
            action.target_version_id or "",
            action.reason or "",
        ),
    )


def _preferred_first_candidates(
    candidates: Sequence[ModVersion],
    preferred_version_id: str | None,
) -> list[ModVersion]:
    if not preferred_version_id:
        return list(candidates)

    preferred = [candidate for candidate in candidates if candidate.version_id == preferred_version_id]
    remaining = [candidate for candidate in candidates if candidate.version_id != preferred_version_id]
    return preferred + remaining


def _find_version_for_action(action: RepairAction, versions: Sequence[ModVersion]) -> ModVersion | None:
    if action.target_version_id:
        for version in versions:
            if version.version_id == action.target_version_id:
                return version

    if action.target_version_number:
        for version in versions:
            if version.mod_id != action.target_mod_id:
                continue
            if version.version_number == action.target_version_number:
                return version
    return None


def _best_partial_priority(
    state: SolverState,
    report: CompatibilityReport,
    original_config: ModpackConfig,
) -> tuple:
    return (
        error_issue_count(report),
        state.total_cost,
        -count_original_mods_preserved(original_config, state.config),
        count_removed_original_mods(original_config, state.config),
        len(state.actions),
        canonical_state_key(state.config),
    )


def _first_mod_id(issue: CompatibilityIssue) -> str | None:
    return issue.affected_mod_ids[0] if issue.affected_mod_ids else None
