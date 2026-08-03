"""Simple baseline repair suggestions for compatibility issues.

These repairs are intentionally non-optimal. They provide straightforward,
demo-ready next steps without comparing complete repair plans or weighted cost.
"""

from __future__ import annotations

from modpack_solver.graph import GraphBuildResult
from modpack_solver.models import CompatibilityIssue, IssueType, RepairAction, RepairActionType


def suggest_baseline_repairs(
    result: GraphBuildResult,
    issues: list[CompatibilityIssue],
) -> list[RepairAction]:
    repairs: list[RepairAction] = []

    for issue in issues:
        if issue.issue_type == IssueType.MISSING_DEPENDENCY:
            target_mod_id = issue.affected_mod_ids[1] if len(issue.affected_mod_ids) > 1 else "unknown-dependency"
            repairs.append(
                RepairAction(
                    action_type=RepairActionType.ADD_DEPENDENCY,
                    target_mod_id=target_mod_id,
                    cost=1,
                    reason=f"Add dependency '{target_mod_id}' because it is required by the selected mod.",
                )
            )

        elif issue.issue_type == IssueType.HARD_CONFLICT:
            target_mod_id = issue.affected_mod_ids[-1] if issue.affected_mod_ids else "conflicting-mod"
            repairs.append(
                RepairAction(
                    action_type=RepairActionType.REMOVE_MOD,
                    target_mod_id=target_mod_id,
                    cost=5,
                    reason=(
                        f"Remove '{target_mod_id}' as a baseline conflict fix. "
                        "This is a simple suggestion, not the future weighted choice."
                    ),
                )
            )

        elif issue.issue_type == IssueType.OPTIONAL_DEPENDENCY_WARNING:
            target_mod_id = issue.affected_mod_ids[1] if len(issue.affected_mod_ids) > 1 else "optional-dependency"
            repairs.append(
                RepairAction(
                    action_type=RepairActionType.ADD_DEPENDENCY,
                    target_mod_id=target_mod_id,
                    cost=0,
                    reason=(
                        f"Optionally add '{target_mod_id}' to improve functionality. "
                        "This is not required for compatibility."
                    ),
                )
            )

        elif issue.issue_type == IssueType.UNKNOWN_DEPENDENCY_TARGET:
            target_mod_id = issue.affected_mod_ids[-1] if issue.affected_mod_ids else "unknown-target"
            repairs.append(
                RepairAction(
                    action_type=RepairActionType.ADD_DEPENDENCY,
                    target_mod_id=target_mod_id,
                    cost=2,
                    reason=(
                        "Fetch more metadata or check the dependency target manually before "
                        "deciding on a concrete repair."
                    ),
                )
            )

        elif issue.issue_type in {IssueType.MINECRAFT_VERSION_MISMATCH, IssueType.LOADER_MISMATCH}:
            target_mod_id = issue.affected_mod_ids[0] if issue.affected_mod_ids else "selected-mod"
            repairs.append(
                RepairAction(
                    action_type=RepairActionType.UPGRADE_MOD,
                    target_mod_id=target_mod_id,
                    cost=3,
                    reason=(
                        f"Search for a version of '{target_mod_id}' that matches the chosen "
                        "Minecraft version and loader."
                    ),
                )
            )

        elif issue.issue_type == IssueType.UNRESOLVED_SELECTED_MOD:
            target_mod_id = issue.affected_mod_ids[0] if issue.affected_mod_ids else "selected-mod"
            repairs.append(
                RepairAction(
                    action_type=RepairActionType.ADD_DEPENDENCY,
                    target_mod_id=target_mod_id,
                    cost=2,
                    reason=(
                        f"Resolve which version of '{target_mod_id}' should be selected by checking "
                        "available metadata."
                    ),
                )
            )

    return _deduplicate_repairs(repairs)


def _deduplicate_repairs(repairs: list[RepairAction]) -> list[RepairAction]:
    seen: set[tuple[str, str, str | None, str | None]] = set()
    deduped: list[RepairAction] = []
    for repair in repairs:
        key = (
            repair.action_type.value,
            repair.target_mod_id,
            repair.target_version_id,
            repair.reason,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(repair)
    return deduped
