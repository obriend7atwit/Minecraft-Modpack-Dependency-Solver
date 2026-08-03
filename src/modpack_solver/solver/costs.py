"""Weighted repair-cost helpers."""

from __future__ import annotations

from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.models import RepairAction, RepairActionType


class RepairWeights(BaseModel):
    """Fixed, reproducible default costs for repair planning."""

    model_config = ConfigDict(extra="forbid")

    add_required_dependency: int = Field(default=1, ge=0)
    upgrade_dependency: int = Field(default=2, ge=0)
    downgrade_dependency: int = Field(default=3, ge=0)
    upgrade_selected_mod: int = Field(default=4, ge=0)
    downgrade_selected_mod: int = Field(default=5, ge=0)
    remove_selected_mod: int = Field(default=10, ge=0)
    change_minecraft_version: int = Field(default=20, ge=0)
    change_loader: int = Field(default=25, ge=0)


def action_cost(
    action: RepairAction,
    weights: RepairWeights,
    *,
    is_dependency: bool | None = None,
) -> int:
    """Return the configured cost for one repair action."""

    if action.action_type == RepairActionType.ADD_DEPENDENCY:
        return weights.add_required_dependency
    if action.action_type == RepairActionType.UPGRADE_DEPENDENCY:
        return weights.upgrade_dependency
    if action.action_type == RepairActionType.DOWNGRADE_DEPENDENCY:
        return weights.downgrade_dependency
    if action.action_type == RepairActionType.UPGRADE_MOD:
        return weights.upgrade_dependency if is_dependency else weights.upgrade_selected_mod
    if action.action_type == RepairActionType.DOWNGRADE_MOD:
        return weights.downgrade_dependency if is_dependency else weights.downgrade_selected_mod
    if action.action_type == RepairActionType.REMOVE_MOD:
        return weights.remove_selected_mod
    if action.action_type == RepairActionType.CHANGE_MINECRAFT_VERSION:
        return weights.change_minecraft_version
    if action.action_type == RepairActionType.CHANGE_LOADER:
        return weights.change_loader
    raise ValueError(f"Unsupported repair action type: {action.action_type!r}")


def plan_cost(
    actions: Sequence[RepairAction],
    weights: RepairWeights,
) -> int:
    """Return the total weighted cost for a repair plan."""

    return sum(action_cost(action, weights) for action in actions)
